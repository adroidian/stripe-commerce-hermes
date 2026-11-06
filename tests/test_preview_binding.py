"""Credential-free, socket-blocked tests of real exposed handlers and transport.

Host UI doubles supply a human decision, never mock the plugin approval gate.
The parent separately tests the genuine Hermes approval bridge.
"""
import concurrent.futures
import importlib
import html
import json
import os
import re
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from human_ui import HumanUI
from test_stripe import KEY, Response, client, plugin, tools

MUTATIONS = {
    "stripe_create_product": {"name": "Tea + cake / café", "description": "One & two"},
    "stripe_archive_product": {"id": "prod_A"},
    "stripe_create_price": {"product_id": "prod_A", "amount_cents": 1299, "currency": "usd", "interval": "month"},
    "stripe_deactivate_price": {"id": "price_A"},
    "stripe_create_payment_link": {"price_id": "price_A", "redirect_url": "https://example.com/done?a=1&b=two"},
    "stripe_deactivate_payment_link": {"id": "plink_A"},
}


class PreviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"STRIPE_API_KEY": KEY})
        self.env.start(); self.addCleanup(self.env.stop)
        self.ui = HumanUI().start(); self.addCleanup(self.ui.stop)
        self.net = patch("urllib.request.OpenerDirector.open")
        self.open = self.net.start(); self.addCleanup(self.net.stop)
        self.open.return_value = Response({"id": "prod_Test"})
        self.sock = patch.object(socket, "socket", side_effect=AssertionError("Real sockets forbidden"))
        self.sock.start(); self.addCleanup(self.sock.stop)
        # Clear only in-memory test state between cases, if the new module exists.
        try:
            self.binding = importlib.import_module("stripe_commerce.write_approval")
        except ModuleNotFoundError:
            self.binding = None
        if self.binding:
            self.binding._pending.clear()
        self.context = {"session_id": "session-A", "task_id": "task-A"}

    def call(self, name, args, **context):
        out = tools.handler(name)(args, **(self.context | context))
        self.assertNotIn(KEY, out)
        return json.loads(out)

    def preview(self, name="stripe_create_product", args=None):
        args = MUTATIONS[name] if args is None else args
        out = self.call(name, dict(args))
        self.assertTrue(out["success"], out)
        return out

    def live(self, name="stripe_create_product", args=None, preview=None, **context):
        args = MUTATIONS[name] if args is None else args
        preview = self.preview(name, args) if preview is None else preview
        return self.call(name, {**args, "preview_id": preview.get("preview_id", "old-implementation-has-no-token"),
                                "dry_run": False}, **context)

    def valid_responses(self, name, args):
        if name == "stripe_create_product":
            obj = {"id": "prod_New", **args}
        elif name == "stripe_create_price":
            obj = {"id": "price_New", "product": args["product_id"], "unit_amount": args["amount_cents"],
                   "currency": args["currency"], "recurring": {"interval": args["interval"]}}
        elif name == "stripe_create_payment_link":
            obj = {"id": "plink_New", "active": True,
                   "after_completion": {"type": "redirect", "redirect": {"url": args["redirect_url"]}},
                   "line_items": {"has_more": False, "data": [{"price": {"id": args["price_id"]}, "quantity": 1}]}}
        else:
            obj = {"id": args["id"], "active": False}
        self.open.side_effect = [Response({"id": obj["id"]}), Response(obj)]

    def blocked(self, result):
        self.assertFalse(result["success"], result)
        self.open.assert_not_called()

    def test_all_six_without_preview_never_prompt_or_send(self):
        for name, args in MUTATIONS.items():
            with self.subTest(tool=name):
                self.blocked(self.call(name, {**args, "dry_run": False}))
        self.ui.consent.assert_not_called(); self.ui.wait.assert_not_called()

    def test_registered_handlers_also_enforce_boundary(self):
        class Registry:
            def __init__(self): self.handlers = {}
            def register_tool(self, **kw): self.handlers[kw["name"]] = kw["handler"]
            def register_skill(self, *args, **kw): pass
        registry = Registry(); plugin.register(registry)
        for name, args in MUTATIONS.items():
            result = json.loads(registry.handlers[name]({**args, "dry_run": False}, **self.context))
            self.blocked(result)

    def test_all_six_preview_is_exact_opaque_offline(self):
        ids = set()
        for name, args in MUTATIONS.items():
            for _ in range(2):
                out = self.preview(name, args)
                token = out.get("preview_id", "")
                self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")
                self.assertNotIn(token, ids); ids.add(token)
                self.assertEqual(out["method"], "POST")
                self.assertEqual(out["origin"], "https://api.stripe.com")
                self.assertEqual(out["encoded_form"], urlencode(sorted(out["would_create_or_update"].items())))
                self.assertEqual(out["expires_in_seconds"], 300)
                self.assertNotIn("id", out)
        self.open.assert_not_called(); self.ui.consent.assert_not_called()

    def test_all_six_valid_exact_post_headers_then_strict_readback(self):
        for name, args in MUTATIONS.items():
            with self.subTest(tool=name):
                self.open.reset_mock(); self.valid_responses(name, args)
                preview = self.preview(name, args)
                result = self.live(name, args, preview)
                self.assertTrue(result["success"], result); self.assertTrue(result["verified"], result)
                post, get = [c.args[0] for c in self.open.call_args_list]
                self.assertEqual(post.method, preview["method"])
                self.assertEqual(post.full_url, preview["origin"] + preview["path"])
                self.assertEqual(post.data, preview["encoded_form"].encode("ascii"))
                self.assertEqual(post.get_header("Authorization"), "Bearer " + KEY)
                self.assertEqual(post.get_header("Idempotency-key"), preview["idempotency_key"])
                self.assertEqual(post.get_header("User-agent"), "stripe-commerce-hermes/0.2.0")
                self.assertEqual(get.method, "GET")
                prompt = self.ui.wait.call_args.args[2]
                self.assertIn(preview["encoded_form"], prompt["command"])
                self.assertIn(preview["origin"] + preview["path"], prompt["command"])
                self.assertIn("mode=test", prompt["command"]); self.assertNotIn(KEY, str(prompt))
                self.assertIn("key-sha256=", prompt["command"])
                consent = self.ui.consent.call_args
                self.assertIsNone(consent.kwargs["remember_key"])
                self.assertLessEqual(sum(len(html.escape(value)) for value in (consent.args[0], consent.args[1], consent.kwargs["title"])) + 300, 750)
                self.assertIs(prompt["allow_permanent"], False)
                self.assertIs(prompt["allow_session"], False)
                self.assertGreater(consent.kwargs["timeout_seconds"], 0)
                self.assertLessEqual(consent.kwargs["timeout_seconds"], 300)
        self.ui.policy.assert_not_called()

    def test_changed_business_fields_rejected_before_prompt(self):
        changes = {
            "stripe_create_product": {"description": "changed"},
            "stripe_create_price": {"amount_cents": 1400},
            "stripe_create_payment_link": {"redirect_url": "https://other.test"},
            "stripe_archive_product": {"id": "prod_Other"},
            "stripe_deactivate_price": {"id": "price_Other"},
            "stripe_deactivate_payment_link": {"id": "plink_Other"},
        }
        for name, args in MUTATIONS.items():
            preview = self.preview(name, args)
            self.blocked(self.live(name, args | changes[name], preview))
        self.ui.consent.assert_not_called()

    def test_each_price_and_link_field_is_bound(self):
        for field, value in (("product_id", "prod_Other"), ("currency", "eur"), ("interval", "year")):
            args = MUTATIONS["stripe_create_price"]
            self.blocked(self.live("stripe_create_price", args | {field: value}, self.preview("stripe_create_price")))
        args = MUTATIONS["stripe_create_payment_link"]
        self.blocked(self.live("stripe_create_payment_link", args | {"price_id": "price_Other"}, self.preview("stripe_create_payment_link")))
        self.ui.consent.assert_not_called()

    def test_wrong_tool_unknown_arbitrary_and_malformed_tokens(self):
        p = self.preview("stripe_archive_product")
        self.blocked(self.live("stripe_deactivate_price", {"id": "price_A"}, p))
        for token in ("A" * 43, "approve", "", 3, True, None, "../preview"):
            self.blocked(self.call("stripe_create_product", {"name": "X", "dry_run": False, "preview_id": token}))
        self.ui.consent.assert_not_called()

    def test_full_key_and_mode_bound_even_when_last4_same(self):
        for key in ("rk_test_Different1234", "rk_live_Different1234"):
            p = self.preview()
            with patch.dict(os.environ, {"STRIPE_API_KEY": key}):
                self.blocked(self.live(preview=p))
        self.ui.consent.assert_not_called()

    def test_session_task_and_host_routing_context_bound(self):
        for change in ({"session_id": "session-B"}, {"task_id": "task-B"}):
            self.blocked(self.live(preview=self.preview(), **change))
        p = self.preview(); self.ui.session_key = "other-human-session"
        self.blocked(self.live(preview=p)); self.ui.consent.assert_not_called()

    def test_expired_before_approval_no_prompt(self):
        with patch.object(time, "monotonic", return_value=1000) as clock:
            p = self.preview(); clock.return_value = 1300
            self.blocked(self.live(preview=p))
        self.ui.consent.assert_not_called()

    def test_expiry_during_approval_and_remaining_gateway_timeout(self):
        with patch.object(time, "monotonic", return_value=1000) as clock:
            p = self.preview(); clock.return_value = 1290
            def expires(*args, **kw):
                self.assertLessEqual(self.ui.consent.call_args.kwargs["timeout_seconds"], 10)
                clock.return_value = 1301
                return {"resolved": True, "choice": "once"}
            self.ui.wait.side_effect = expires
            self.blocked(self.live(preview=p))
            self.ui.wait.assert_called_once()

    def test_pending_capacity_and_expiry_cleanup(self):
        with patch.object(time, "monotonic", return_value=1000) as clock:
            for _ in range(256): self.preview()
            self.blocked(self.call("stripe_create_product", MUTATIONS["stripe_create_product"]))
            clock.return_value = 1301
            self.assertIn("preview_id", self.preview())
        self.open.assert_not_called()

    def test_restart_invalidates_preview(self):
        p = self.preview()
        assert self.binding is not None
        importlib.reload(self.binding)
        self.blocked(self.live(preview=p)); self.ui.consent.assert_not_called()

    def test_only_native_accept_is_authority_and_denial_consumes(self):
        choices = ("decline", "cancel", "deny", "timeout", "cancelled", "always", "session", "once", None, True, {}, [], "approved", "ACCEPT")
        for choice in choices:
            p = self.preview(); self.ui.consent.return_value = choice; self.ui.consent.side_effect = None
            self.blocked(self.live(preview=p))
            self.ui.consent.return_value = "accept"
            self.blocked(self.live(preview=p))
        self.assertEqual(self.ui.consent.call_count, len(choices))

    def test_ui_error_consumes_preview(self):
        p = self.preview(); self.ui.wait.side_effect = RuntimeError("private " + KEY)
        self.blocked(self.live(preview=p)); self.ui.wait.side_effect = None
        self.blocked(self.live(preview=p)); self.ui.wait.assert_called_once()

    def test_no_gateway_or_no_user_or_delegation_blocks_autoapproval(self):
        for kind in ("gateway", "no_user", "delegation"):
            with self.subTest(kind=kind):
                p = self.preview()
                if kind == "gateway": self.ui.callbacks.clear()
                self.ui.no_user = kind == "no_user"; self.ui.delegated = kind == "delegation"
                with patch.dict(os.environ, {"HERMES_YOLO_MODE": "1"}): self.blocked(self.live(preview=p))
                self.ui.gateway(); self.ui.no_user = False; self.ui.delegated = False
        self.ui.consent.assert_not_called(); self.ui.policy.assert_not_called()

    def test_missing_incompatible_host_fails_closed(self):
        p = self.preview()
        with patch.dict("sys.modules", {"tools.approval_prompt": None}): self.blocked(self.live(preview=p))
        p = self.preview(); self.ui.wait.side_effect = TypeError("old host API")
        self.blocked(self.live(preview=p))

    def test_gateway_uses_unique_one_operation_ui_payload(self):
        self.ui.gateway()
        for _ in range(2):
            p = self.preview(); self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
            self.assertTrue(self.live(preview=p)["verified"])
            call = self.ui.wait.call_args
            self.assertEqual(call.args[:2], (self.ui.session_key, self.ui.notify))
            data = call.args[2]
            self.assertIn(p["preview_id"], data["command"])
            self.assertEqual(data["pattern_keys"], [data["pattern_key"]])
            self.assertIs(data["allow_permanent"], False); self.assertIs(data["allow_session"], False)
            self.assertEqual(call.kwargs, {"surface": "stripe-commerce"})
            self.assertIn(p["encoded_form"], data["command"])
        keys = [c.args[2]["command"] for c in self.ui.wait.call_args_list]
        self.assertEqual(len(set(keys)), 2)
        self.ui.prompt.assert_not_called(); self.ui.policy.assert_not_called()

    def test_gateway_denial_timeout_unresolved_malformed_cancelled(self):
        self.ui.gateway()
        for decision in (None, True, [], "once", {}, {"choice": "once"},
                         {"resolved": True, "choice": "deny"}, {"resolved": False, "choice": "once"},
                         {"resolved": True, "choice": "once", "cancelled": "closed"},
                         {"resolved": True, "choice": "once", "notify_failed": True}):
            self.ui.wait.return_value = decision
            self.blocked(self.live())

    def test_gateway_unattended_and_delegated_still_block(self):
        self.ui.gateway()
        for kind in ("no_user", "delegated"):
            setattr(self.ui, kind, True)
            self.blocked(self.live())
            setattr(self.ui, kind, False)
        self.ui.wait.assert_not_called()

    def test_after_approval_key_context_and_interrupt_rechecked(self):
        for change in ("key", "context", "interrupt"):
            p = self.preview()
            def mutate(*args, **kw):
                if change == "key": os.environ["STRIPE_API_KEY"] = "rk_test_Changed1234"
                if change == "context": self.ui.session_key = "changed"
                if change == "interrupt": self.ui.interrupted = True
                return {"resolved": True, "choice": "once"}
            self.ui.wait.side_effect = mutate
            self.blocked(self.live(preview=p))
            os.environ["STRIPE_API_KEY"] = KEY; self.ui.session_key = "human-session"; self.ui.interrupted = False

    def test_interrupt_before_prompt(self):
        p = self.preview(); self.ui.interrupted = True
        self.blocked(self.live(preview=p)); self.ui.consent.assert_not_called()

    def test_mutable_caller_args_cannot_change_captured_post_or_verification(self):
        p = self.preview(); args = {**MUTATIONS["stripe_create_product"], "preview_id": p.get("preview_id"), "dry_run": False}
        def mutate(*a, **kw):
            args.update(name="ATTACK", description="changed", dry_run=True, preview_id="new")
            return {"resolved": True, "choice": "once"}
        self.ui.wait.side_effect = mutate
        self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
        result = self.call("stripe_create_product", args)
        self.assertTrue(result["verified"], result)
        self.assertEqual(self.open.call_args_list[0].args[0].data, p["encoded_form"].encode())

    def test_replay_after_success_or_transport_error_never_reprompts(self):
        for fail in (False, True):
            self.open.reset_mock(); p = self.preview()
            if fail: self.open.side_effect = OSError("uncertain private " + KEY)
            else: self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
            first = self.live(preview=p)
            self.assertEqual(first["success"], not fail)
            before = self.open.call_count; prompts = self.ui.wait.call_count
            self.assertFalse(self.live(preview=p)["success"])
            self.assertEqual(self.open.call_count, before); self.assertEqual(self.ui.wait.call_count, prompts)
            self.assertEqual(before, 1 if fail else 2)

    def test_atomic_claim_race_only_one_prompt_and_post(self):
        p = self.preview(); entered = threading.Event(); release = threading.Event()
        def wait(*args, **kw):
            entered.set()
            self.assertTrue(release.wait(3))
            return {"resolved": True, "choice": "once"}
        self.ui.wait.side_effect = wait
        self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(self.live, preview=p)
            self.assertTrue(entered.wait(3))
            two = pool.submit(self.live, preview=p)
            second = two.result(timeout=3)
            self.assertFalse(second["success"]); self.open.assert_not_called()
            release.set(); first = one.result(timeout=3)
        self.assertTrue(first["verified"], first)
        self.ui.wait.assert_called_once(); self.assertEqual(self.open.call_count, 2)

    def test_transport_rotation_after_approval_before_request_build_aborts(self):
        p = self.preview(); original = client.urllib.request.build_opener
        def rotate(*a, **kw):
            opener = original(*a, **kw)
            os.environ["STRIPE_API_KEY"] = "rk_test_Rotated1234"
            return opener
        with patch.object(client.urllib.request, "build_opener", side_effect=rotate):
            self.blocked(self.live(preview=p))

    def test_all_six_preview_references_without_human_ui_do_not_send(self):
        self.ui.callbacks.clear(); self.ui.callback = None
        for name, args in MUTATIONS.items():
            with self.subTest(tool=name):
                self.blocked(self.live(name, args))
        self.ui.consent.assert_not_called(); self.ui.policy.assert_not_called()

    def test_gateway_expiry_during_human_wait_blocks_and_consumes(self):
        self.ui.gateway()
        with patch.object(time, "monotonic", return_value=1000) as clock:
            p = self.preview()
            def expired(*args, **kw):
                clock.return_value = 1300
                return {"resolved": True, "choice": "once"}
            self.ui.wait.side_effect = expired
            self.blocked(self.live(preview=p))
            self.blocked(self.live(preview=p))
            self.ui.wait.assert_called_once()

    def test_final_transport_preflight_rechecks_expiry_context_interrupt(self):
        original = client.urllib.request.build_opener
        for change in ("expiry", "profile", "interrupt"):
            with self.subTest(change=change), patch.object(time, "monotonic", return_value=1000) as clock:
                p = self.preview()
                def mutate(*args, **kw):
                    opener = original(*args, **kw)
                    if change == "expiry": clock.return_value = 1300
                    if change == "profile": self.ui.profile_home = "/unit-test/changed"
                    if change == "interrupt": self.ui.interrupted = True
                    return opener
                with patch.object(client.urllib.request, "build_opener", side_effect=mutate):
                    self.blocked(self.live(preview=p))
                self.ui.profile_home = "/unit-test/profile-A"; self.ui.interrupted = False

    def test_origin_change_never_sends(self):
        p = self.preview()
        with patch.object(client, "ORIGIN", "https://other.test"):
            self.blocked(self.live(preview=p))
        self.ui.consent.assert_not_called()

    def test_model_cannot_supply_an_approval_argument(self):
        p = self.preview()
        self.blocked(self.call("stripe_create_product", {**MUTATIONS["stripe_create_product"],
            "preview_id": p.get("preview_id"), "dry_run": False, "approved": True}))
        self.ui.consent.assert_not_called()

    def test_preview_and_human_text_redact_secret_shaped_values(self):
        p = self.preview(args={"name": KEY})
        self.assertNotIn(KEY, json.dumps(p))
        self.ui.wait.return_value = {"resolved": True, "choice": "deny"}
        self.blocked(self.live(args={"name": KEY}, preview=p))
        self.ui.consent.assert_not_called()  # Hidden redacted fields cannot be approved exactly.

    def test_host_display_redaction_refuses_hidden_non_stripe_values(self):
        for platform in ("telegram", "discord"):
            self.ui.platform = platform
            for prefix in ("ghp_", "sk-"):
                with self.subTest(platform=platform, prefix=prefix):
                    value = prefix + "a" * 20  # Synthetic provider-token shape.
                    args = {"name": value}
                    p = self.preview(args=args)
                    self.ui.display.side_effect = lambda text, **kw: text.replace(value, "[MASKED]")
                    self.valid_responses("stripe_create_product", args)
                    self.blocked(self.live(args=args, preview=p))
                    self.blocked(self.live(args=args, preview=p))  # Consumed on refusal.
                    self.ui.consent.assert_not_called()
                    self.ui.display.assert_called()
                    self.assertTrue(all(c.kwargs == {"force": True} for c in self.ui.display.call_args_list))

    def test_missing_native_display_integrity_api_blocks_writes(self):
        import sys
        p = self.preview()
        self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
        with patch.dict(sys.modules, {"agent.redact": None}):
            self.blocked(self.live(preview=p))
        self.ui.consent.assert_not_called()

    def test_native_display_integrity_error_or_non_string_blocks_writes(self):
        for failure in (TypeError("Incompatible display API"), None, False):
            with self.subTest(failure=type(failure).__name__):
                p = self.preview()
                if isinstance(failure, Exception):
                    self.ui.display.side_effect = failure
                else:
                    self.ui.display.side_effect = None
                    self.ui.display.return_value = failure
                self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                self.blocked(self.live(preview=p))
                self.ui.consent.assert_not_called()

    def test_oversized_description_or_redirect_cannot_hide_tail_from_human(self):
        cases = [("stripe_create_product", {"name": "X", "description": "a" * 1800 + "CHARGE TAIL"}),
                 ("stripe_create_payment_link", {"price_id": "price_A", "redirect_url": "https://example.com/" + "a" * 1800 + "evil"})]
        for name, args in cases:
            p = self.preview(name, args)
            result = self.live(name, args, p)
            self.blocked(result)
            self.assertIn("display limit", result["error"])
        self.ui.consent.assert_not_called()

    def test_profile_home_bound_before_and_after_approval(self):
        p = self.preview(); self.ui.profile_home = "/unit-test/profile-B"
        self.blocked(self.live(preview=p)); self.ui.consent.assert_not_called()
        p = self.preview()
        def change(*args, **kw):
            self.ui.profile_home = "/unit-test/profile-C"
            return "accept"
        self.ui.consent.side_effect = change
        self.blocked(self.live(preview=p))

    def test_scoped_key_overrides_process_environment_and_redacts(self):
        scoped_key = "rk_test_ProfileScoped5678"
        self.ui.scope_key = scoped_key
        self.assertEqual(client.require_key(), scoped_key)
        self.assertTrue(plugin.key_ready())
        self.assertNotIn(scoped_key, client.redact({"message": scoped_key}))
        p = self.preview(); self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
        self.assertTrue(self.live(preview=p)["verified"])
        self.assertEqual(self.open.call_args_list[0].args[0].get_header("Authorization"), "Bearer " + scoped_key)

    def test_scoped_resolver_error_never_falls_back_to_process_key(self):
        self.ui.secret.side_effect = RuntimeError("secret scope missing")
        self.assertFalse(plugin.key_ready())
        self.blocked(self.call("stripe_create_product", {"name": "X"}))
        with self.assertRaises(client.StripeError): client.require_key()
        self.assertNotIn(KEY, client.redact({"message": KEY}))

    def test_scoped_key_rotation_during_approval_aborts(self):
        self.ui.scope_key = "rk_test_ProfileA1234"
        p = self.preview()
        def change(*args, **kw):
            self.ui.scope_key = "rk_test_ProfileB1234"
            return "accept"
        self.ui.consent.side_effect = change
        self.blocked(self.live(preview=p))

    def test_r2_all_six_cli_tui_callbacks_refused_before_ui_or_http(self):
        for platform in ("", "cli", "tui"):
            self.ui.platform = platform
            self.ui.callbacks.clear()
            for name, args in MUTATIONS.items():
                with self.subTest(platform=platform, tool=name):
                    # Even a custom callback claiming full-prompt display is
                    # not attestation of a supported native renderer.
                    self.valid_responses(name, args)
                    self.blocked(self.live(name, args))
        self.ui.consent.assert_not_called(); self.ui.callback.assert_not_called()
        self.ui.prompt.assert_not_called(); self.ui.wait.assert_not_called()

    def test_r2_all_six_qq_and_unverified_gateways_refused_before_ui_or_http(self):
        self.ui.gateway()
        for platform in ("qqbot", "qq", "slack", "matrix", "unknown", "", "Telegram", "telegram "):
            self.ui.platform = platform
            for name, args in MUTATIONS.items():
                with self.subTest(platform=platform, tool=name):
                    # Reproduce the valid-length QQ hidden-tail request too.
                    if name == "stripe_create_product":
                        args = {"name": "A" * 200 + "HIDDEN_TAIL"}
                    self.valid_responses(name, args)
                    self.blocked(self.live(name, args))
        self.ui.consent.assert_not_called(); self.ui.wait.assert_not_called()
        self.ui.prompt.assert_not_called()

    def test_r2_all_six_telegram_discord_exact_happy_writes(self):
        self.ui.gateway()
        for platform in ("telegram", "discord"):
            self.ui.platform = platform
            for name, args in MUTATIONS.items():
                with self.subTest(platform=platform, tool=name):
                    self.open.reset_mock(); self.ui.consent.reset_mock(); self.ui.wait.reset_mock()
                    p = self.preview(name, args); self.valid_responses(name, args)
                    result = self.live(name, args, p)
                    self.assertTrue(result["success"], result); self.assertTrue(result["verified"], result)
                    self.assertEqual(self.open.call_count, 2)
                    post, get = [c.args[0] for c in self.open.call_args_list]
                    self.assertEqual(post.data, p["encoded_form"].encode("ascii"))
                    self.assertEqual(post.full_url, p["origin"] + p["path"])
                    self.assertEqual(post.get_header("Idempotency-key"), p["idempotency_key"])
                    self.assertEqual(post.get_header("Authorization"), "Bearer " + KEY)
                    self.assertEqual(get.method, "GET")
                    self.assertIn(p["encoded_form"], self.ui.wait.call_args.args[2]["command"])
                    self.ui.consent.assert_called_once(); self.ui.wait.assert_called_once()
        self.ui.prompt.assert_not_called(); self.ui.policy.assert_not_called()

    def test_r2_platform_change_before_claim_invalidates_and_consumes(self):
        self.ui.gateway()
        for original, changed in (("telegram", "discord"), ("discord", "telegram"),
                                  ("telegram", "qqbot"), ("qqbot", "telegram"), ("", "discord")):
            with self.subTest(original=original, changed=changed):
                self.ui.platform = original; p = self.preview()
                self.ui.platform = changed
                self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                self.blocked(self.live(preview=p))
                self.ui.platform = original
                self.blocked(self.live(preview=p))
        self.ui.consent.assert_not_called(); self.ui.wait.assert_not_called()

    def test_r2_platform_change_during_ui_invalidates(self):
        self.ui.gateway()
        for original, changed in (("telegram", "discord"), ("discord", "telegram"), ("telegram", "qqbot")):
            with self.subTest(original=original, changed=changed):
                self.ui.platform = original; p = self.preview()
                def change(*args, **kw):
                    self.ui.platform = changed
                    return "accept"
                self.ui.consent.side_effect = change
                self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                self.blocked(self.live(preview=p))
                self.ui.platform = original
                self.blocked(self.live(preview=p))
        self.assertEqual(self.ui.consent.call_count, 3)

    def test_r2_platform_change_post_tls_before_http_invalidates(self):
        self.ui.gateway()
        original_opener = client.urllib.request.build_opener
        for original, changed in (("telegram", "discord"), ("discord", "telegram"), ("telegram", "qqbot")):
            with self.subTest(original=original, changed=changed):
                self.ui.platform = original; p = self.preview()
                def change(*args, **kw):
                    opener = original_opener(*args, **kw)
                    self.ui.platform = changed
                    return opener
                self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                with patch.object(client.urllib.request, "build_opener", side_effect=change):
                    self.blocked(self.live(preview=p))
                self.ui.platform = original
                self.blocked(self.live(preview=p))
        self.assertEqual(self.ui.consent.call_count, 3)

    def test_r2_missing_platform_api_keeps_reads_previews_but_blocks_writes(self):
        self.ui.gateway()
        mod = self.ui.modules["tools.approval_context"]
        if hasattr(mod, "_get_session_platform"):
            del mod._get_session_platform
        self.assertTrue(self.call("stripe_whoami", {})["success"])
        self.open.reset_mock()
        for name, args in MUTATIONS.items():
            self.valid_responses(name, args)
            self.blocked(self.live(name, args))  # preview itself must still work
        self.ui.consent.assert_not_called()

    def test_r2_incompatible_platform_api_keeps_reads_previews_but_blocks_writes(self):
        self.ui.gateway()
        mod = self.ui.modules["tools.approval_context"]
        class StrSubclass(str): pass
        for value in (None, False, True, 1, [], {}, StrSubclass("telegram")):
            with self.subTest(value=repr(value)):
                mod._get_session_platform = lambda: value
                self.open.return_value = Response({"id": "acct_Test"}); self.open.side_effect = None
                self.assertTrue(self.call("stripe_whoami", {})["success"])
                self.open.reset_mock()
                self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                self.blocked(self.live())
        def incompatible(): raise TypeError("Unsupported platform API")
        mod._get_session_platform = incompatible
        self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
        self.blocked(self.live())
        self.ui.consent.assert_not_called()

    def test_r2_ambiguous_human_gateway_signals_are_not_authority(self):
        self.ui.gateway(); self.ui.platform = "telegram"
        mod = self.ui.modules["tools.approval_context"]
        for name, values in (("_no_user_can_answer", (None, 0, "")),
                             ("_is_gateway_approval_context", (None, 1, "yes"))):
            original = getattr(mod, name)
            for value in values:
                with self.subTest(api=name, value=value), patch.object(mod, name, return_value=value):
                    self.valid_responses("stripe_create_product", MUTATIONS["stripe_create_product"])
                    self.blocked(self.live())
            setattr(mod, name, original)
        self.ui.consent.assert_not_called()

    def test_delegation_autoapprove_callback_is_not_human(self):
        def autoapprove(*args, **kw): return "once"
        autoapprove.__module__ = "tools.delegate_tool_config"
        self.ui.callback = autoapprove; self.ui.callbacks.clear(); self.ui.platform = ""
        self.blocked(self.live()); self.ui.consent.assert_not_called()


if __name__ == "__main__": unittest.main()
