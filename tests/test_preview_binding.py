"""Native public migration: real dispatcher/policy/queue/redactor/handlers.
Only human delivery/answers and Stripe HTTP are simulated; sockets denied.
"""
import concurrent.futures
import contextvars
import html
import json
import os
import threading
import time
from unittest.mock import patch
from urllib.parse import urlencode
import pytest
from . import test_stripe as baseline
from .test_stripe import KEY, Response, client, plugin, tools

MUTATIONS = {
    "stripe_create_product": {"name": "Tea + cake", "description": "One & two"},
    "stripe_archive_product": {"id": "prod_A"},
    "stripe_create_price": {"product_id": "prod_A", "amount_cents": 1299, "currency": "usd", "interval": "month"},
    "stripe_deactivate_price": {"id": "price_A"},
    "stripe_create_payment_link": {"price_id": "price_A", "redirect_url": "https://example.com/done"},
    "stripe_deactivate_payment_link": {"id": "plink_A"},
}

class Case:
    def __init__(self, base):
        self.base = base
        self.ui, self.open, self.binding = base.human_ui, base.open, plugin.write_approval
    def call(self, name, args, **kw):
        out = self.ui.dispatch(name, args, **kw)
        assert KEY not in out
        return json.loads(out)
    def preview(self, name="stripe_create_product", args=None):
        result = self.call(name, dict(MUTATIONS[name] if args is None else args))
        assert result["success"], result
        return result
    def live(self, name="stripe_create_product", args=None, preview=None, **kw):
        args = MUTATIONS[name] if args is None else args
        p = self.preview(name, args) if preview is None else preview
        return self.call(name, {**args, "preview_id": p["preview_id"], "dry_run": False}, **kw)
    def responses(self, name="stripe_create_product", args=None):
        args = MUTATIONS[name] if args is None else args
        if name == "stripe_create_product": obj = {"id": "prod_New", **args}
        elif name == "stripe_create_price":
            obj = {"id": "price_New", "product": args["product_id"], "unit_amount": args["amount_cents"], "currency": args["currency"], "recurring": {"interval": args["interval"]} if "interval" in args else None}
        elif name == "stripe_create_payment_link":
            obj = {"id": "plink_New", "active": True, "after_completion": {"type": "redirect", "redirect": {"url": args["redirect_url"]}} if "redirect_url" in args else {"type": "hosted_confirmation"}, "line_items": {"has_more": False, "data": [{"price": {"id": args["price_id"]}, "quantity": 1}]}}
        else: obj = {"id": args["id"], "active": False}
        self.open.side_effect = [Response({"id": obj["id"]}), Response(obj)]
    def blocked(self, result):
        assert not result.get("success", False), result
        self.open.assert_not_called()

@pytest.fixture
def c():
    base = baseline.StripeTests(methodName="runTest")
    base.setUp()
    try: yield Case(base)
    finally: base.doCleanups()

@pytest.mark.parametrize("platform", ["telegram", "discord"])
@pytest.mark.parametrize("name", MUTATIONS)
def test_public_migration_all_six_native_success_exact_bytes(c, platform, name):
    c.ui.platform = platform; args = MUTATIONS[name]
    p = c.preview(name, args); c.responses(name, args)
    result = c.live(name, args, p)
    assert result["success"] and result["verified"], result
    post, get = [call.args[0] for call in c.open.call_args_list]
    assert post.method == "POST" and get.method == "GET"
    assert post.full_url == p["origin"] + p["path"]
    assert post.data == p["encoded_form"].encode("ascii")
    assert post.get_header("Idempotency-key") == p["idempotency_key"]
    assert post.get_header("Authorization") == "Bearer " + KEY
    assert post.get_header("User-agent") == "stripe-commerce-hermes/0.2.0"
    data = c.ui.notify.call_args.args[0]
    assert json.loads(data["command"]) == {"tool": name, "args": {**args, "preview_id": p["preview_id"], "dry_run": False}}
    assert p["encoded_form"] in data["description"]
    assert p["origin"] + p["path"] in data["description"]
    assert "test key-sha256=" in data["description"]
    assert len(html.escape(data["description"])) <= 300
    assert len(html.escape(data["command"])) + len(html.escape(data["description"])) + 500 <= 1800
    assert data["allow_permanent"] is False and data["allow_session"] is False
    c.ui.notify.assert_called_once()

@pytest.mark.parametrize("name", MUTATIONS)
def test_missing_preview_and_direct_registered_handler(c, name):
    args = MUTATIONS[name]
    c.blocked(c.call(name, {**args, "dry_run": False}))
    p = c.preview(name, args)
    c.blocked(json.loads(c.ui.model_tools.registry.dispatch(name, {**args, "preview_id": p["preview_id"], "dry_run": False}, session_id="session-A", task_id="task-A")))
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("name", MUTATIONS)
def test_preview_exact_opaque_offline(c, name):
    p, q = c.preview(name), c.preview(name)
    assert len(p["preview_id"]) == 43 and p["preview_id"] != q["preview_id"]
    assert p["method"] == "POST" and p["origin"] == "https://api.stripe.com"
    assert p["encoded_form"] == urlencode(sorted(p["would_create_or_update"].items()))
    assert p["expires_in_seconds"] == 300 and "id" not in p
    c.open.assert_not_called(); c.ui.notify.assert_not_called()

@pytest.mark.parametrize("name", MUTATIONS)
def test_every_business_field_bound_and_mismatch_consumes(c, name):
    args = MUTATIONS[name]
    for field, value in args.items():
        changed = value + 1 if type(value) is int else {"currency": "eur", "interval": "year"}.get(field, value + "Other")
        p = c.preview(name, args)
        c.blocked(c.live(name, {**args, field: changed}, p)); c.blocked(c.live(name, args, p))
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("token", ["A" * 43, "approve", "", 3, True, None, "../preview"])
def test_arbitrary_token(c, token):
    c.blocked(c.call("stripe_create_product", {"name": "X", "dry_run": False, "preview_id": token}))
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("key", ["rk_test_Different1234", "rk_live_Different1234"])
def test_full_key_mode_bound(c, key):
    p = c.preview()
    with patch.dict(os.environ, {"STRIPE_API_KEY": key}): c.blocked(c.live(preview=p))
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("change", [{"session_id": "session-B"}, {"task_id": "task-B"}])
def test_session_task_bound(c, change):
    c.blocked(c.live(preview=c.preview(), **change)); c.ui.notify.assert_not_called()

@pytest.mark.parametrize("phase", ["before", "wait", "opener"])
def test_expiry_at_each_local_guard(c, phase):
    with patch.object(time, "monotonic", return_value=1000) as clock:
        p = c.preview()
        if phase == "before": clock.return_value = 1300
        if phase == "wait": c.ui.on_prompt = lambda data: setattr(clock, "return_value", 1300)
        original = client.urllib.request.build_opener
        def build(*args, **kw):
            result = original(*args, **kw)
            if phase == "opener": clock.return_value = 1300
            return result
        with patch.object(client.urllib.request, "build_opener", side_effect=build): c.blocked(c.live(preview=p))
        c.blocked(c.live(preview=p))

@pytest.mark.parametrize("choice", ["deny", "session", "always", "timeout", "cancelled", "unavailable", None, True, "approved"])
def test_native_only_once_and_denial_consumes(c, choice):
    p = c.preview(); c.ui.choice = choice
    c.blocked(c.live(preview=p)); c.ui.choice = "once"
    c.blocked(c.live(preview=p)); c.ui.notify.assert_called_once()

@pytest.mark.parametrize("mode", ["timeout", "exception", "missing"])
def test_native_delivery_failures(c, mode):
    from tools import approval_gateway_wait
    if mode == "exception": c.ui.notify.side_effect = RuntimeError("simulated delivery exception")
    if mode == "missing": c.ui.approval.unregister_gateway_notify(c.ui.session_key)
    if mode == "timeout": c.ui.notify.side_effect = None
    with patch.object(approval_gateway_wait, "_poll_event", return_value="timeout"):
        p = c.preview(); c.blocked(c.live(preview=p)); c.blocked(c.live(preview=p))

@pytest.mark.parametrize("policies", [None, "mandatory", {}, frozenset(), ["mandatory"]])
def test_unsupported_invalid_host_read_preview_only(c, policies):
    from hermes_cli import plugins
    with patch.object(plugins, "VALID_TOOL_APPROVAL_POLICIES", policies):
        assert c.call("stripe_whoami", {})["success"]
        c.open.reset_mock(); c.blocked(c.live())
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("mode", ["off", "smart", "manual"])
def test_yolo_remembered_do_not_skip_native_gate(c, mode):
    from tools import approval
    from hermes_cli import config
    with patch.dict(os.environ, {"HERMES_YOLO_MODE": "1"}), patch.object(approval, "is_approved", return_value=True), patch.object(approval, "_persist_choice", side_effect=AssertionError("must not persist")), patch.object(config, "load_config_readonly", return_value={"approvals": {"mode": mode}}):
        c.responses(); assert c.live()["verified"]
    c.ui.notify.assert_called_once()

@pytest.mark.parametrize("flag", ["HERMES_CRON_SESSION", "HERMES_SINGLE_QUERY_SESSION"])
def test_native_unattended_no_autoapproval(c, flag):
    p = c.preview()
    with patch.dict(os.environ, {"HERMES_YOLO_MODE": "1"}): c.blocked(c.live(preview=p, env={flag: "1"}))
    c.ui.notify.assert_not_called()

def test_delegated_callback_is_not_human(c):
    from tools.terminal_tool import set_approval_callback
    def autoapprove(*args, **kw): return "once"
    autoapprove.__module__ = "tools.delegate_tool_config"
    set_approval_callback(autoapprove)
    try:
        c.ui.approval.unregister_gateway_notify(c.ui.session_key)
        c.blocked(c.live(env={"HERMES_INTERACTIVE": "1"}))
    finally: set_approval_callback(None)

@pytest.mark.parametrize("kind", ["key", "profile", "surface"])
@pytest.mark.parametrize("phase", ["wait", "opener"])
def test_scope_rotation_at_each_local_guard(c, kind, phase):
    p = c.preview()
    def change(*args):
        if kind == "key": os.environ["STRIPE_API_KEY"] = "rk_test_Changed1234"
        if kind == "profile": os.environ["HERMES_HOME"] = client.profile_home() + "-changed"
        if kind == "surface": os.environ["HERMES_SESSION_PLATFORM"] = "discord"
    if phase == "wait": c.ui.on_prompt = change
    original = client.urllib.request.build_opener
    def build(*args, **kw):
        result = original(*args, **kw)
        if phase == "opener": change()
        return result
    with patch.dict(os.environ), patch.object(client.urllib.request, "build_opener", side_effect=build): c.blocked(c.live(preview=p))

def test_mutable_caller_detached_snapshot(c):
    p = c.preview(); args = {**MUTATIONS["stripe_create_product"], "preview_id": p["preview_id"], "dry_run": False}
    c.ui.on_prompt = lambda data: args.update(name="ATTACK", description="changed")
    c.responses(); assert c.call("stripe_create_product", args)["verified"]
    assert c.open.call_args_list[0].args[0].data == p["encoded_form"].encode()

@pytest.mark.parametrize("fail", [False, True])
def test_replay_after_success_uncertainty_no_retry(c, fail):
    p = c.preview()
    if fail: c.open.side_effect = OSError("uncertain dummy")
    else: c.responses()
    assert c.live(preview=p)["success"] is not fail
    count = c.open.call_count
    assert not c.live(preview=p).get("success", False)
    assert c.open.call_count == count == (1 if fail else 2)
    c.ui.notify.assert_called_once()

def test_atomic_claim_race(c):
    p = c.preview(); entered = threading.Event(); release = threading.Event()
    def wait(data): entered.set(); assert release.wait(5)
    c.ui.on_prompt = wait; c.responses()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(c.live, preview=p); assert entered.wait(5)
        second = pool.submit(c.live, preview=p).result(timeout=5)
        assert not second.get("success", False); c.open.assert_not_called()
        release.set(); first = one.result(timeout=5)
    assert first["verified"]; assert c.open.call_count == 2; c.ui.notify.assert_called_once()

@pytest.mark.parametrize("prefix", ["ghp_", "sk-"])
def test_native_provider_masking_even_redaction_off(c, prefix):
    from agent import redact
    args = {"name": prefix + "a" * 40}; p = c.preview(args=args)
    with patch.object(redact, "_REDACT_ENABLED", False, create=True): c.blocked(c.live(args=args, preview=p))
    c.ui.notify.assert_called_once(); assert args["name"] not in c.ui.notify.call_args.args[0]["command"]

def test_native_registered_dummy_vault_masking(c):
    value = "dummy-vault-plain-value-13579"
    c.ui.ctx.register_redaction_patterns([value])
    args = {"name": value}; p = c.preview(args=args)
    c.blocked(c.live(args=args, preview=p)); assert value not in c.ui.notify.call_args.args[0]["command"]

@pytest.mark.parametrize("value", ["café", "Tea ``` hidden", "Tea\u202e hidden", "a" * 250])
def test_unsafe_or_oversize_display(c, value):
    p = c.preview(args={"name": value}); c.blocked(c.live(args={"name": value}, preview=p)); c.ui.notify.assert_not_called()

@pytest.mark.parametrize("platform", ["", "cli", "tui", "qq", "qqbot", "slack", "matrix", "Telegram", "unknown"])
def test_unqualified_surfaces_all_six_preview_only(c, platform):
    c.ui.platform = platform
    for name, args in MUTATIONS.items(): c.blocked(c.live(name, args))
    c.ui.notify.assert_not_called()

@pytest.mark.parametrize("old,new", [("telegram", "discord"), ("discord", "telegram"), ("qq", "telegram")])
def test_surface_switch_before_claim_consumes(c, old, new):
    c.ui.platform = old; p = c.preview(); c.ui.platform = new; c.blocked(c.live(preview=p))
    c.ui.platform = old; c.blocked(c.live(preview=p)); c.ui.notify.assert_not_called()

@pytest.mark.parametrize("skip", [{"skip_pre_tool_call_hook": True}, {"skip_tool_execution_middleware": True}])
def test_skipped_hook_or_execution_middleware_no_lease(c, skip): c.blocked(c.live(**skip))

@pytest.mark.parametrize("hook", ["pre_approval_request", "post_approval_response"])
def test_missing_observer_no_lease(c, hook):
    c.ui.manager._hooks[hook].clear(); c.blocked(c.live())

def test_middleware_fail_open_cannot_send(c):
    def broken(**kw): raise RuntimeError("incompatible middleware")
    c.ui.manager._middleware["tool_execution"][:] = [broken]; c.blocked(c.live()); c.ui.notify.assert_called_once()

@pytest.mark.parametrize("before", [False, True])
def test_modify_hooks_before_after_do_not_authorize(c, before):
    callback = lambda **kw: {"action": "modify", "args": {"name": "CHANGED"}} if kw["args"].get("dry_run") is False else None
    hooks = c.ui.manager._hooks["pre_tool_call"]
    hooks.insert(0 if before else len(hooks), callback)
    c.blocked(c.live())

@pytest.mark.parametrize("directive", [{"action": "block", "message": "other veto"}, {"action": "approve", "message": "different", "rule_key": "other", "approval_policy": "mandatory"}])
def test_competing_veto_or_later_mandatory_override(c, directive):
    c.ui.ctx.register_hook("pre_tool_call", lambda **kw: directive if kw["args"].get("dry_run") is False else None)
    p = c.preview(); c.blocked(c.live(preview=p)); c.blocked(c.live(preview=p))

@pytest.mark.parametrize("kind", ["tool_request", "tool_execution"])
def test_request_and_final_execution_rewrite(c, kind):
    def modify(args, next_call=None, **kw):
        changed = {**args, "description": "CHANGED"} if args.get("dry_run") is False else args
        return next_call(changed) if next_call else {"args": changed}
    c.ui.ctx.register_middleware(kind, modify); c.blocked(c.live())

@pytest.mark.parametrize("hook", ["agent_loop_stopped", "on_session_reset", "on_session_finalize", "on_session_end", "on_session_delete"])
def test_lifecycle_invalidates_pending_and_waiting(c, hook):
    p = c.preview(); c.ui.manager.invoke_hook(hook, session_id="session-A"); c.blocked(c.live(preview=p))
    p = c.preview(); c.ui.on_prompt = lambda data: c.ui.manager.invoke_hook(hook, session_id="session-A")
    c.blocked(c.live(preview=p))

def test_late_worker_invalidation_cannot_revive(c):
    original = c.binding.request_message
    def late(pending): c.binding.invalidate(session_id="session-A"); return original(pending)
    with patch.object(c.binding, "request_message", side_effect=late): c.blocked(c.live())
    assert not c.binding._attempts; c.ui.notify.assert_not_called()

def test_copied_context_lease_cannot_escape(c):
    captured = []
    def capture(args, next_call, **kw): captured.append(contextvars.copy_context()); return next_call(args)
    c.ui.ctx.register_middleware("tool_execution", capture)
    c.responses(); p = c.preview(); assert c.live(preview=p)["verified"]
    count = c.open.call_count
    result = captured[-1].run(tools.handler("stripe_create_product"), {**MUTATIONS["stripe_create_product"], "preview_id": p["preview_id"], "dry_run": False}, session_id="session-A", task_id="task-A")
    assert not json.loads(result)["success"]; assert c.open.call_count == count

def test_capacity_restart_origin_and_model_approval(c):
    with patch.object(time, "monotonic", return_value=1000) as clock:
        for _ in range(256): c.preview()
        c.blocked(c.call("stripe_create_product", {"name": "X"})); clock.return_value = 1301; p = c.preview()
    c.binding._pending.clear(); c.blocked(c.live(preview=p))
    p = c.preview()
    with patch.object(client, "ORIGIN", "https://other.test"): c.blocked(c.live(preview=p))
    p = c.preview(); c.blocked(c.call("stripe_create_product", {"name": "X", "preview_id": p["preview_id"], "dry_run": False, "approved": True}))
    c.ui.notify.assert_not_called()
