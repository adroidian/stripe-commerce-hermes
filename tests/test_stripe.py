import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stripe_commerce", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
from stripe_commerce import stripe_client as client, tools

KEY = "rk_test_UnitTestSecret1234"

class Response:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def geturl(self): return "https://api.stripe.com/v1/account"
    def read(self, n): return self.body[:n]

class StripeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"STRIPE_API_KEY": KEY})
        self.env.start()
        self.transport = patch("urllib.request.OpenerDirector.open")
        self.open = self.transport.start()
        self.open.return_value = Response({"id": "acct_123"})
        self.addCleanup(self.env.stop)
        self.addCleanup(self.transport.stop)
    def call(self, tool_name, **args):
        result = tools.handler(tool_name)(args, session_id="ignored")
        self.assertNotIn(KEY, result)
        return json.loads(result)
    def test_reject_secret_keys(self):
        for key in ("sk_live_Forbidden1234", "sk_test_Forbidden1234", "pk_test_123", "rk_unknown_123", "rk_test_", ""):
            with self.subTest(key=key), patch.dict(os.environ, {"STRIPE_API_KEY": key}):
                result = self.call("stripe_whoami")
                self.assertFalse(result["success"])
                self.assertIn("restricted", result["error"])
        self.open.assert_not_called()
    def test_guard_on_registration(self):
        with patch.dict(os.environ, {"STRIPE_API_KEY": "sk_live_Forbidden1234"}):
            with self.assertRaises(client.StripeError): plugin.register(object())
    def test_registration_and_manifest_surface(self):
        class Ctx:
            def __init__(self): self.tools = []; self.skills = []
            def register_tool(self, **kw): self.tools.append(kw)
            def register_skill(self, *args, **kw): self.skills.append(args)
        ctx = Ctx(); plugin.register(ctx)
        self.assertEqual(len(ctx.tools), 13)
        self.assertEqual(len(ctx.skills), 1)
        for tool in ctx.tools:
            self.assertEqual(tool["requires_env"], ["STRIPE_API_KEY"])
            self.assertTrue(tool["check_fn"]())
        self.open.assert_not_called()
    def test_accept_test_key(self):
        result = self.call("stripe_whoami")
        self.assertEqual(result["mode"], "test")
        self.assertEqual(result["key_last4"], "1234")
        self.assertEqual(result["account_id"], "acct_123")
    def test_accept_live_key(self):
        with patch.dict(os.environ, {"STRIPE_API_KEY": "rk_live_Fixture1234"}):
            self.assertEqual(self.call("stripe_whoami")["mode"], "live")
    def test_rotation_guard(self):
        call = tools.handler("stripe_list_products")
        with patch.dict(os.environ, {"STRIPE_API_KEY": "sk_test_Forbidden1234"}):
            self.assertFalse(json.loads(call({}))["success"])
        self.open.assert_not_called()
    def test_all_mutations_default_dry(self):
        cases = {"stripe_create_product": {"name": "Test"},
                 "stripe_create_price": {"product_id": "prod_A", "amount_cents": 500, "currency": "usd"},
                 "stripe_create_payment_link": {"price_id": "price_A"},
                 "stripe_archive_product": {"id": "prod_A"},
                 "stripe_deactivate_price": {"id": "price_A"},
                 "stripe_deactivate_payment_link": {"id": "plink_A"}}
        for name, args in cases.items():
            self.assertTrue(self.call(name, **args)["dry_run"])
            self.assertTrue(self.call(name, **args, dry_run=True)["dry_run"])
        self.open.assert_not_called()
    def test_dry_run_still_guards_key(self):
        with patch.dict(os.environ, {"STRIPE_API_KEY": "sk_live_Forbidden1234"}):
            self.assertFalse(self.call("stripe_create_product", name="Test", dry_run=True)["success"])
        self.open.assert_not_called()
    def test_price_encoding_and_readback(self):
        obj = {"id": "price_New", "product": "prod_A", "unit_amount": 1299, "currency": "usd", "recurring": {"interval": "month"}}
        self.open.side_effect = [Response(obj), Response(obj)]
        result = self.call("stripe_create_price", product_id="prod_A", amount_cents=1299, currency="usd", interval="month", dry_run=False)
        self.assertTrue(result["verified"])
        req = self.open.call_args_list[0].args[0]
        self.assertEqual(parse_qs(req.data.decode()), {"product": ["prod_A"], "unit_amount": ["1299"], "currency": ["usd"], "recurring[interval]": ["month"]})
        self.assertEqual(req.full_url, "https://api.stripe.com/v1/prices")
        self.assertEqual(self.open.call_args_list[1].args[0].method, "GET")
    def test_archive_readback(self):
        obj = {"id": "prod_A", "active": False}
        self.open.side_effect = [Response(obj), Response(obj)]
        self.assertTrue(self.call("stripe_archive_product", id="prod_A", dry_run=False)["verified"])
        self.assertEqual(parse_qs(self.open.call_args_list[0].args[0].data.decode()), {"active": ["false"]})
    def test_write_readback_failure_preserves_id(self):
        self.open.side_effect = [Response({"id": "prod_A"}), URLError("secret " + KEY)]
        result = self.call("stripe_create_product", name="Test", dry_run=False)
        self.assertEqual(result["id"], "prod_A")
        self.assertFalse(result["verified"])
    def test_readback_mismatch(self):
        self.open.side_effect = [Response({"id": "prod_A"}), Response({"id": "prod_A", "name": "Different"})]
        self.assertFalse(self.call("stripe_create_product", name="Test", dry_run=False)["verified"])
    def test_invalid_amounts(self):
        for amount in (True, 0, -1, 100000000, 1.5, "100"):
            self.assertFalse(self.call("stripe_create_price", product_id="prod_A", amount_cents=amount, currency="usd")["success"])
        self.open.assert_not_called()
    def test_invalid_id_no_http(self):
        for val in ("prod_A/../../refunds", "https://evil.test", "prod_A?expand=x", "price_A"):
            self.assertFalse(self.call("stripe_archive_product", id=val)["success"])
        self.open.assert_not_called()
    def test_boolean_dry_run_strict(self):
        self.assertFalse(self.call("stripe_create_product", name="Test", dry_run="false")["success"])
        self.open.assert_not_called()
    def test_invalid_redirects(self):
        for url in ("http://example.com", "https://u:p@example.com", "//evil.test", "https://example.com/\n"):
            self.assertFalse(self.call("stripe_create_payment_link", price_id="price_A", redirect_url=url)["success"])
        self.open.assert_not_called()
    def test_redirect_url_not_fetched(self):
        result = self.call("stripe_create_payment_link", price_id="price_A", redirect_url="https://example.com/thanks?x=1")
        self.assertEqual(result["would_create_or_update"]["line_items[0][quantity]"], 1)
        self.open.assert_not_called()
    def test_http_errors_json(self):
        for code in (400, 401, 403, 429, 500):
            self.open.side_effect = HTTPError("https://api.stripe.com", code, KEY, {}, io.BytesIO(KEY.encode()))
            self.assertFalse(self.call("stripe_whoami")["success"])
    def test_network_failure_json(self):
        self.open.side_effect = URLError(KEY)
        self.assertFalse(self.call("stripe_whoami")["success"])
    def test_malformed_response(self):
        for body in (b"invalid", b"[]", b'{"error": {}}', b"x" * (client.MAX_BYTES + 1)):
            self.open.return_value = Response(body)
            self.assertFalse(self.call("stripe_whoami")["success"])
    def test_output_redaction(self):
        self.open.return_value = Response({"data": [{"id": "prod_A", "name": KEY + " sk_live_OtherSecret1234"}], "has_more": False})
        result = tools.handler("stripe_list_products")({})
        self.assertNotIn(KEY, result)
        self.assertNotIn("sk_live_OtherSecret1234", result)
        self.assertIn("REDACTED", result)
    def test_no_pii_expansion(self):
        self.open.return_value = Response({"id": "sub_A", "customer": {"email": "private@example.com"}, "metadata": {"secret": KEY}, "status": "active"})
        result = self.call("stripe_get_subscription", id="sub_A")
        self.assertNotIn("customer", result)
        self.assertNotIn("metadata", result)
    def test_endpoint_allowlist(self):
        for method, path in (("POST", "/v1/refunds"), ("GET", "/v1/balance"), ("POST", "/v1/subscriptions/sub_A"), ("GET", "https://evil.test"), ("DELETE", "/v1/products/prod_A")):
            with self.assertRaises(client.StripeError): client.request(method, path)
        self.open.assert_not_called()
    def test_redirect_block(self):
        with self.assertRaises(client.StripeError):
            client.NoRedirect().redirect_request(None, None, 302, "Redirect", {}, "https://evil.test")
    def test_no_proxy_and_verified_tls(self):
        with patch("urllib.request.build_opener", wraps=client.urllib.request.build_opener) as build:
            self.call("stripe_whoami")
            handlers = build.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertTrue(handlers[2]._context.check_hostname)
    def test_pagination(self):
        self.open.return_value = Response({"data": [{"id": "prod_Last", "name": "Sample"}], "has_more": True})
        result = self.call("stripe_list_products", starting_after="prod_First")
        self.assertEqual(result["next_starting_after"], "prod_Last")
        self.assertIn("starting_after=prod_First", self.open.call_args.args[0].full_url)
    def test_portal_summary(self):
        self.open.return_value = Response({"data": [{"id": "bpc_A", "object": "billing_portal.configuration", "features": {"subscription_cancel": {"enabled": True}}}], "has_more": False})
        result = self.call("stripe_portal_config")
        self.assertTrue(result["exists"])
        self.assertTrue(result["data"][0]["cancellation_enabled"])
    def test_subscription_status_validation(self):
        self.assertFalse(self.call("stripe_list_subscriptions", status="invented")["success"])
        self.open.assert_not_called()
    def test_unknown_arguments(self):
        self.assertFalse(self.call("stripe_create_product", name="Test", url="https://evil.test")["success"])
        self.open.assert_not_called()
    def test_missing_key_check_and_registration(self):
        class Ctx:
            def register_tool(self, **kwargs): pass
            def register_skill(self, *args, **kwargs): pass
        with patch.dict(os.environ, {"STRIPE_API_KEY": ""}):
            self.assertFalse(plugin.key_ready())
            plugin.register(Ctx())
            self.assertFalse(self.call("stripe_whoami")["success"])
        self.open.assert_not_called()
    def test_currency_and_interval_checks(self):
        for args in ({"currency": "USD"}, {"currency": "us"}, {"currency": "usd", "interval": "minute"}):
            self.assertFalse(self.call("stripe_create_price", **{"product_id": "prod_A", "amount_cents": 100, **args})["success"])
        self.open.assert_not_called()
    def test_malformed_list_json_error(self):
        for body in ({"data": {}}, {"data": ["bad"]}, {}):
            self.open.return_value = Response(body)
            self.assertFalse(self.call("stripe_list_products")["success"])
    def test_no_write_id_is_not_success(self):
        self.open.return_value = Response({"object": "product"})
        self.assertFalse(self.call("stripe_create_product", name="Test", dry_run=False)["success"])
        self.assertEqual(self.open.call_count, 1)
    def test_unexpected_response_origin(self):
        response = Response({"id": "acct_123"})
        response.geturl = lambda: "https://evil.test/v1/account"
        self.open.return_value = response
        self.assertFalse(self.call("stripe_whoami")["success"])
    def test_unknown_tool_and_bad_args(self):
        self.assertFalse(self.call("stripe_refund")["success"])
        self.assertFalse(json.loads(tools.handler("stripe_whoami")([]))["success"])

if __name__ == "__main__": unittest.main()
