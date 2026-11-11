"""Additional native correlation, lifecycle and public compatibility edges."""
import json
import os
import threading
import concurrent.futures
from unittest.mock import patch
import pytest
from .test_preview_binding import c  # shared native fixture
from .test_stripe import KEY, plugin, client

@pytest.mark.parametrize("field", ["command", "description", "session_id", "turn_id", "tool_call_id", "session_key", "surface", "pattern_keys"])
def test_complete_observer_payload_and_correlation_required(c, field):
    original = c.binding._observe
    def altered(post, **kw):
        if post: kw[field] = ["wrong"] if field == "pattern_keys" else str(kw.get(field, "")) + "CHANGED"
        return original(post, **kw)
    with patch.object(c.binding, "_observe", side_effect=altered): c.blocked(c.live())

@pytest.mark.parametrize("hook", ["pre_approval_request", "post_approval_response"])
def test_observer_callback_exception_not_approval(c, hook):
    def failed(**kw): raise RuntimeError("failed observer")
    c.ui.manager._hooks[hook][:] = [failed]; c.blocked(c.live())

def test_custom_transport_matching_once_unqualified(c):
    from hermes_cli import config
    shown = []
    def present(request): shown.append(request); return request.respond("once")
    c.ui.ctx.register_approval_transport("dummy", present)
    with patch.object(config, "load_config_readonly", return_value={"security": {"approval": {"transport": "dummy"}}}): c.blocked(c.live())
    assert len(shown) == 1; c.ui.notify.assert_not_called()

def test_two_previews_need_two_once_choices(c):
    a, b = c.preview(), c.preview()
    c.responses(); assert c.live(preview=a)["verified"]
    first = c.ui.notify.call_args.args[0]["pattern_key"]
    c.responses(); assert c.live(preview=b)["verified"]
    assert first != c.ui.notify.call_args.args[0]["pattern_key"]
    assert c.ui.notify.call_count == 2


def test_native_none_task_id_normalizes_to_hook_empty_string(c):
    from .test_preview_binding import MUTATIONS
    args = MUTATIONS["stripe_create_product"]
    p = c.call("stripe_create_product", args, task_id=None)
    assert p["success"]
    c.responses()
    assert c.live(preview=p, task_id=None)["verified"]

def test_unused_approval_retired_after_skipped_middleware(c):
    p = c.preview(); c.blocked(c.live(preview=p, tool_call_id="same", skip_tool_execution_middleware=True))
    assert not c.binding._attempts
    c.blocked(c.live(preview=p, tool_call_id="same", skip_pre_tool_call_hook=True)); c.ui.notify.assert_called_once()

@pytest.mark.parametrize("value", [None, False, True, 1, [], {}, "Telegram"])
def test_missing_invalid_surface_read_preview_only(c, value):
    with patch.object(c.binding, "_surface", return_value=value):
        assert c.call("stripe_whoami", {})["success"]
        c.open.reset_mock(); c.blocked(c.live())
    c.ui.notify.assert_not_called()

def test_surface_accessor_exception_blocks_only_execution(c):
    with patch.object(c.binding, "_surface", side_effect=TypeError("incompatible surface")): c.blocked(c.live())
    c.ui.notify.assert_not_called()

def test_scoped_key_positive_and_rotation(c):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    token = set_secret_scope({"STRIPE_API_KEY": "rk_test_Scoped5678"})
    try:
        p = c.preview(); c.responses(); assert c.live(preview=p)["verified"]
        assert c.open.call_args_list[0].args[0].get_header("Authorization") == "Bearer rk_test_Scoped5678"
        c.open.reset_mock(); p = c.preview(); replacement = []
        c.ui.on_prompt = lambda data: replacement.append(set_secret_scope({"STRIPE_API_KEY": "rk_test_Rotated5678"}))
        try: c.blocked(c.live(preview=p))
        finally:
            if replacement: reset_secret_scope(replacement[0])
    finally: reset_secret_scope(token)

def test_scoped_resolver_error_no_fallback(c):
    from agent import secret_scope
    with patch.object(secret_scope, "get_secret", side_effect=RuntimeError("no scope")):
        assert not plugin.key_ready(); c.blocked(c.call("stripe_create_product", {"name": "X"}))

def test_stripe_secret_display_model_redaction(c):
    p = c.preview(args={"name": KEY}); assert KEY not in json.dumps(p)
    c.blocked(c.live(args={"name": KEY}, preview=p)); c.ui.notify.assert_not_called()

def test_wrong_tool_profile_long_redirect_bound(c):
    p = c.preview("stripe_archive_product"); c.blocked(c.live("stripe_deactivate_price", {"id": "price_A"}, p))
    p = c.preview()
    with patch.dict(os.environ, {"HERMES_HOME": client.profile_home() + "-other"}): c.blocked(c.live(preview=p))
    args = {"price_id": "price_A", "redirect_url": "https://example.com/" + "a" * 1800 + "TAIL"}
    p = c.preview("stripe_create_payment_link", args); c.blocked(c.live("stripe_create_payment_link", args, p)); c.ui.notify.assert_not_called()


def test_real_host_timed_out_pretool_worker_cannot_authorize_later(c):
    from hermes_cli import plugins
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = c.binding.request_message
    def delayed(pending):
        entered.set()
        try:
            assert release.wait(5)
            return original(pending)
        finally: finished.set()
    p = c.preview()
    with patch.object(plugins, "_resolve_hook_callback_timeout", return_value=0.02), patch.object(c.binding, "request_message", side_effect=delayed):
        try:
            c.blocked(c.live(preview=p, tool_call_id="timed-out"))
            assert entered.is_set()
        finally:
            release.set(); assert finished.wait(5)
    # A late record is not a grant: no approval observers or normal admitted
    # middleware existed. Even same IDs + skipped hooks cannot resurrect it.
    c.blocked(c.live(preview=p, tool_call_id="timed-out", skip_pre_tool_call_hook=True))
    c.ui.notify.assert_not_called()


def test_inflight_reservation_counts_towards_capacity(c):
    entered, release = threading.Event(), threading.Event()
    original = c.binding.request_message
    p = c.preview()
    for _ in range(255): c.preview()
    def delayed(pending):
        entered.set(); assert release.wait(5)
        return original(pending)
    c.ui.choice = "deny"
    with patch.object(c.binding, "request_message", side_effect=delayed), concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(c.live, preview=p)
        try:
            assert entered.wait(5)
            c.blocked(c.call("stripe_create_product", {"name": "No room"}))
        finally: release.set()
        assert not worker.result(timeout=5).get("success", False)
    assert not c.binding._reservations


def test_concurrent_independent_previews_require_independent_once(c):
    from .test_stripe import Response
    barrier = threading.Barrier(2)
    c.ui.on_prompt = lambda data: barrier.wait(timeout=5)
    a, b = c.preview(), c.preview()
    c.open.side_effect = None
    c.open.return_value = Response({"id": "prod_New", "name": "Tea + cake", "description": "One & two"})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda p: c.live(preview=p), [a, b]))
    assert all(r["verified"] for r in results), results
    assert c.ui.notify.call_count == 2
    assert len({call.args[0]["pattern_key"] for call in c.ui.notify.call_args_list}) == 2
    posts = [call.args[0] for call in c.open.call_args_list if call.args[0].method == "POST"]
    assert len(posts) == 2
    assert {p.get_header("Idempotency-key") for p in posts} == {a["idempotency_key"], b["idempotency_key"]}
