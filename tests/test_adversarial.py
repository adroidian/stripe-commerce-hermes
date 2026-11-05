"""Transport-mocked regressions for adversarial findings SC-01..SC-03."""
import copy
import io
import json
import unittest
from urllib.error import HTTPError

import test_stripe as baseline
from test_stripe import Response, client, tools, KEY


class AdversarialTests(unittest.TestCase):
    setUp = baseline.StripeTests.setUp
    call = baseline.StripeTests.call

    def price(self):
        return {"id": "price_New", "product": "prod_A", "unit_amount": 1299,
                "currency": "usd", "recurring": {"interval": "month"}}

    def link(self):
        return {"id": "plink_New", "active": True,
                "line_items": {"data": [{"price": {"id": "price_A"}, "quantity": 1}], "has_more": False},
                "after_completion": {"type": "redirect", "redirect": {"url": "https://example.com/thanks"}}}

    def write(self, obj, link=False, redirect=True):
        self.open.side_effect = [Response({"id": obj["id"]}), Response(obj)]
        if link:
            args = {"price_id": "price_A", "dry_run": False}
            if redirect:
                args["redirect_url"] = "https://example.com/thanks"
            return self.call("stripe_create_payment_link", **args)
        return self.call("stripe_create_price", product_id="prod_A", amount_cents=1299,
                         currency="usd", interval="month", dry_run=False)

    def test_sc01_recurring_interval_mismatch(self):
        obj = self.price(); obj["recurring"]["interval"] = "year"
        self.assertFalse(self.write(obj)["verified"])

    def test_sc01_recurring_interval_missing(self):
        obj = self.price(); del obj["recurring"]
        result = self.write(obj)
        self.assertFalse(result["verified"])
        self.assertIn("recurring.interval", result["unverifiable_fields"])

    def test_sc01_payment_link_commercial_mismatches(self):
        for field, value in (("price", {"id": "price_Other"}), ("quantity", 2), ("quantity", True)):
            with self.subTest(field=field, value=value):
                obj = self.link(); obj["line_items"]["data"][0][field] = value
                self.assertFalse(self.write(obj, link=True)["verified"])
        for patch in ({"active": False}, {"active": 1},
                      {"after_completion": {"type": "hosted_confirmation"}},
                      {"after_completion": {"type": "redirect", "redirect": {"url": "https://other.test"}}}):
            with self.subTest(patch=patch):
                self.assertFalse(self.write({**self.link(), **patch}, link=True)["verified"])

    def test_sc01_payment_link_unverifiable_expansion(self):
        for field in ("line_items", "active", "after_completion"):
            with self.subTest(field=field):
                obj = self.link(); del obj[field]
                result = self.write(obj, link=True)
                self.assertFalse(result["verified"])
                self.assertTrue(result["unverifiable_fields"])
                self.assertEqual(result["id"], "plink_New")

    def test_sc01_payment_link_complete_readback(self):
        self.assertTrue(self.write(self.link(), link=True)["verified"])
        self.assertIn("expand%5B%5D=line_items", self.open.call_args.args[0].full_url)

    def test_sc01_payment_link_default_completion(self):
        obj = self.link(); obj["after_completion"] = {"type": "hosted_confirmation"}
        self.assertTrue(self.write(obj, link=True, redirect=False)["verified"])
        self.assertFalse(self.write(self.link(), link=True, redirect=False)["verified"])

    def test_sc01_payment_link_incomplete_or_extra_items(self):
        for mutate in (lambda x: x.update(has_more=True), lambda x: x["data"].append(copy.deepcopy(x["data"][0])),
                       lambda x: x.update(data=[])):
            obj = self.link(); mutate(obj["line_items"])
            self.assertFalse(self.write(obj, link=True)["verified"])

    def test_sc01_other_requested_price_fields_and_one_time(self):
        for field, value in (("product", "prod_Other"), ("unit_amount", 999), ("currency", "eur")):
            obj = self.price(); obj[field] = value
            self.assertFalse(self.write(obj)["verified"])
        obj = self.price(); obj["recurring"] = None
        self.open.side_effect = [Response({"id": obj["id"]}), Response(obj)]
        self.assertTrue(self.call("stripe_create_price", product_id="prod_A", amount_cents=1299,
                                  currency="usd", dry_run=False)["verified"])

    def test_sc01_failed_link_readback_has_unverifiable_fields(self):
        self.open.side_effect = [Response({"id": "plink_New"}), OSError("private " + KEY)]
        result = self.call("stripe_create_payment_link", price_id="price_A", dry_run=False)
        self.assertFalse(result["verified"])
        self.assertIn("active", result["unverifiable_fields"])
        self.assertIn("line_items.price", result["unverifiable_fields"])

    def test_sc02_all_list_endpoints_use_strict_pagination(self):
        for name in ("stripe_list_products", "stripe_list_prices", "stripe_list_payment_links",
                     "stripe_list_subscriptions", "stripe_portal_config"):
            self.open.return_value = Response({"data": [], "has_more": "false"})
            self.assertFalse(self.call(name)["success"])

    def test_sc02_strict_pagination(self):
        cases = [{"data": [], "has_more": flag} for flag in ("false", 0, 1, None, [], {})]
        cases += [{"data": [], "has_more": True}, {"data": [],},
                  {"data": [{"id": "prod_A"}] * 26, "has_more": False},
                  {"data": [{"id": "prod_First"}], "has_more": True},
                  {"data": [{"id": "prod_First"}, {"id": "prod_Last"}], "has_more": True},
                  {"data": [{"id": "price_Wrong"}], "has_more": True},
                  {"data": [{}], "has_more": True},
                  {"data": [{"id": "prod_A"}] * 2, "has_more": True}]
        for body in cases:
            with self.subTest(body=body):
                self.open.return_value = Response(body)
                result = self.call("stripe_list_products", starting_after="prod_First")
                self.assertFalse(result["success"])
                self.assertIn("pagination", result["error"].lower())

    def test_sc02_valid_terminal_and_full_pages(self):
        for rows in ([], [{"id": "prod_A" + str(i)} for i in range(25)]):
            self.open.return_value = Response({"data": rows, "has_more": False})
            result = self.call("stripe_list_products")
            self.assertTrue(result["success"])
            self.assertIsNone(result["next_starting_after"])

    def http_error(self, error, status=400, headers=None):
        self.open.side_effect = HTTPError("https://api.stripe.com/private", status, "NEVER ECHO " + KEY,
                                         headers or {}, io.BytesIO(json.dumps(error).encode()))
        return self.call("stripe_whoami")

    def test_sc03_safe_error_details(self):
        for code, param in (("currency_not_supported", "currency"), ("resource_missing", "price"),
                            ("permission_denied", None)):
            error = {"type": "invalid_request_error", "code": code, "param": param,
                     "message": "NEVER ECHO " + KEY, "doc_url": "https://private.test"}
            result = self.http_error({"error": error})
            self.assertFalse(result["success"])
            self.assertEqual(result["error_details"], {k: v for k, v in error.items() if k in ("type", "code", "param") and v is not None})
            self.assertNotIn("NEVER ECHO", json.dumps(result))
            self.assertNotIn("https://", json.dumps(result))

    def test_sc03_retry_after_bounds(self):
        for header, expected in (("12", 12), ("999999999999999999999", 3600), ("-4", 0), ("0", 0)):
            result = self.http_error({}, status=429, headers={"Retry-After": header})
            self.assertEqual(result["error_details"], {"retry_after_seconds": expected})
        for header in ("1.2", "tomorrow", "https://private.test", "1" * 1000):
            self.assertNotIn("error_details", self.http_error({}, status=429, headers={"Retry-After": header}))

    def test_sc03_malicious_and_malformed_details(self):
        for value in (True, 1, [], {}, None, "x" * 129, "https://private.test", KEY,
                      "prefix_sk_live_Secret123", "Bearer abc", "line\nbreak"):
            result = self.http_error({"error": {"type": value, "code": value, "param": value, "message": KEY}})
            self.assertNotIn("error_details", result)
        for body in ([], {"error": []}, {"error": "bad"}):
            self.assertNotIn("error_details", self.http_error(body))

    def test_sc03_bounded_body_generic_fallback(self):
        for body in (b"not-json", b"x" * (client.MAX_BYTES + 1)):
            self.open.side_effect = HTTPError("https://api.stripe.com", 400, "private", {}, io.BytesIO(body))
            result = self.call("stripe_whoami")
            self.assertFalse(result["success"])
            self.assertNotIn("error_details", result)


if __name__ == "__main__":
    unittest.main()
