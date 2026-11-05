"""Explicit catalog operations. Every handler returns redacted JSON, including failures."""
import re
from urllib.parse import urlsplit
from . import stripe_client as client

S = {"type": "string"}
B = {"type": "boolean"}
PAGE = {"starting_after": S}
DRY = {"dry_run": {"type": "boolean", "default": True,
                    "description": "Default true: validate and preview, without HTTP. Set false only with merchant approval."}}
SPECS = {
    "stripe_whoami": ("Restricted key fingerprint, mode and Stripe account ID. Read-only.", {}, []),
    "stripe_list_products": ("Read up to 25 products; follow next_starting_after when has_more.", PAGE, []),
    "stripe_create_product": ("Create a catalog product, not a charge. Defaults to dry run.", {"name": S, "description": S, **DRY}, ["name"]),
    "stripe_archive_product": ("Archive a product (active=false). Does not cancel subscriptions. Defaults to dry run.", {"id": S, **DRY}, ["id"]),
    "stripe_list_prices": ("Read up to 25 prices; amounts are Stripe integer minor units.", {"product_id": S, **PAGE}, []),
    "stripe_create_price": ("Create a price. amount_cents means integer minor units, not always cents (JPY uses yen). Defaults to dry run.", {"product_id": S, "amount_cents": {"type": "integer", "minimum": 1, "maximum": 99999999}, "currency": S, "interval": {"type": "string", "enum": ["day", "week", "month", "year"]}, **DRY}, ["product_id", "amount_cents", "currency"]),
    "stripe_deactivate_price": ("Deactivate a price (active=false). Existing subscriptions continue. Defaults to dry run.", {"id": S, **DRY}, ["id"]),
    "stripe_create_payment_link": ("Create a hosted checkout link for ONE unit of a price. A customer can later pay through it. Defaults to dry run.", {"price_id": S, "redirect_url": S, **DRY}, ["price_id"]),
    "stripe_list_payment_links": ("Read up to 25 payment links; follow next_starting_after when has_more.", {"active_only": B, **PAGE}, []),
    "stripe_deactivate_payment_link": ("Deactivate a payment link (active=false). Defaults to dry run.", {"id": S, **DRY}, ["id"]),
    "stripe_list_subscriptions": ("Read up to 25 subscriptions; no cancellation or payment operations.", {"status": {"type": "string", "enum": ["incomplete", "incomplete_expired", "trialing", "active", "past_due", "canceled", "unpaid", "paused", "all", "ended"]}, **PAGE}, []),
    "stripe_get_subscription": ("Read subscription state, without customer personal data or payment methods.", {"id": S}, ["id"]),
    "stripe_portal_config": ("Read up to 25 portal configurations and cancellation settings. No portal session creation.", PAGE, []),
}
SCHEMAS = {name: {"name": name, "description": desc, "parameters": {
    "type": "object", "properties": props, "required": required, "additionalProperties": False}}
    for name, (desc, props, required) in SPECS.items()}


def identifier(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r"_[A-Za-z0-9]{1,200}", value):
        raise client.StripeError("Invalid Stripe object ID; expected " + prefix + "_ prefix.")
    return value


def validate(name, args):
    if name not in SPECS or not isinstance(args, dict):
        raise client.StripeError("Unknown tool or invalid arguments.")
    _, props, required = SPECS[name]
    if set(args) - set(props) or any(k not in args for k in required):
        raise client.StripeError("Unexpected or missing tool arguments.")
    for key, value in args.items():
        schema = props[key]
        typ = schema["type"]
        if ((typ == "string" and not isinstance(value, str)) or
            (typ == "boolean" and type(value) is not bool) or
            (typ == "integer" and type(value) is not int)):
            raise client.StripeError("Invalid argument type: " + key)
        if typ == "string" and (not value.strip() or len(value) > 2000):
            raise client.StripeError("Empty or oversized argument: " + key)
        if "enum" in schema and value not in schema["enum"]:
            raise client.StripeError("Unsupported value for " + key)
        if typ == "integer" and not schema["minimum"] <= value <= schema["maximum"]:
            raise client.StripeError("Amount must be 1..99999999 integer minor units.")
    for field, prefix in (("product_id", "prod"), ("price_id", "price")):
        if field in args:
            identifier(args[field], prefix)
    if "id" in args:
        identifier(args["id"], "prod" if "product" in name else "price" if "price" in name else "plink" if "payment_link" in name else "sub")
    if "starting_after" in args:
        identifier(args["starting_after"], "prod" if name.endswith("products") else "price" if name.endswith("prices") else "plink" if name.endswith("payment_links") else "sub" if name.endswith("subscriptions") else "bpc")
    if "currency" in args and not re.fullmatch(r"[a-z]{3}", args["currency"]):
        raise client.StripeError("Currency must be a lowercase three-letter Stripe-supported code; support is checked by Stripe on execution.")
    if "name" in args and len(args["name"]) > 250:
        raise client.StripeError("Product name exceeds 250 characters.")
    if "redirect_url" in args:
        url = urlsplit(args["redirect_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or any(ord(c) < 33 for c in args["redirect_url"]):
            raise client.StripeError("redirect_url must be an absolute HTTPS URL without credentials or whitespace. It is stored at Stripe, never fetched by this plugin.")


def project(obj):
    # Deliberately exclude metadata, customer PII, payment details and arbitrary API expansions.
    keys = ("id", "object", "name", "description", "active", "livemode", "product",
            "unit_amount", "currency", "type", "url", "status", "cancel_at_period_end",
            "current_period_end", "created")
    result = {k: obj[k] for k in keys if k in obj and not isinstance(obj[k], (dict, list))}
    if isinstance(obj.get("recurring"), dict):
        result["recurring"] = {k: obj["recurring"][k] for k in ("interval", "interval_count") if k in obj["recurring"]}
    if obj.get("object") == "billing_portal.configuration":
        result["cancellation_enabled"] = obj.get("features", {}).get("subscription_cancel", {}).get("enabled", False)
    return result


def listing(path, params):
    raw = client.request("GET", path, params)
    rows = raw.get("data")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise client.StripeError("Invalid Stripe list response.")
    more = raw.get("has_more")
    if type(more) is not bool or len(rows) > 25:
        raise client.StripeError("Invalid Stripe pagination: expected boolean has_more and at most 25 rows.")
    prefix = {"/v1/products": "prod", "/v1/prices": "price", "/v1/payment_links": "plink",
              "/v1/subscriptions": "sub", "/v1/billing_portal/configurations": "bpc"}[path]
    try:
        ids = [identifier(row.get("id"), prefix) for row in rows]
    except client.StripeError:
        raise client.StripeError("Invalid Stripe pagination: missing or invalid cursor ID.") from None
    # Stripe IDs are opaque, not lexically ordered. A returned request cursor or
    # duplicate row is evidence of a repeated/regressing page, not forward progress.
    if len(ids) != len(set(ids)) or params.get("starting_after") in ids or (more and not ids):
        raise client.StripeError("Invalid Stripe pagination: empty, repeated or regressing cursor; no forward progress.")
    return {"data": [project(row) for row in rows], "has_more": more,
            "next_starting_after": ids[-1] if more else None}


def verify_readback(obj, object_id, prefix, body):
    """Fail closed on absent evidence; never equate bools with integer quantities."""
    missing, mismatched = [], []

    def compare(path, expected):
        value = obj
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                missing.append(path)
                return
            value = value[part]
        if type(value) is not type(expected) or value != expected:
            mismatched.append(path)

    compare("id", object_id)
    if body.get("active") == "false":
        compare("active", False)
    elif prefix == "prod":
        for field in ("name", "description"):
            if field in body:
                compare(field, body[field])
    elif prefix == "price":
        for field in ("product", "unit_amount", "currency"):
            compare(field, body[field])
        if "recurring[interval]" in body:
            compare("recurring.interval", body["recurring[interval]"])
        else:
            compare("recurring", None)
    else:
        compare("active", True)
        completion = body.get("after_completion[type]", "hosted_confirmation")
        compare("after_completion.type", completion)
        if completion == "redirect":
            compare("after_completion.redirect.url", body["after_completion[redirect][url]"])
        items = obj.get("line_items")
        if not isinstance(items, dict) or type(items.get("has_more")) is not bool or not isinstance(items.get("data"), list):
            missing.extend(["line_items.price", "line_items.quantity"])
        elif items["has_more"]:
            missing.append("line_items.complete")
        elif len(items["data"]) != 1:
            mismatched.append("line_items.count")
        else:
            row = items["data"][0]
            # Reuse strict nested comparison without projecting or exposing expansions.
            if not isinstance(row, dict):
                missing.extend(["line_items.price", "line_items.quantity"])
            else:
                price = row.get("price")
                price = price.get("id") if isinstance(price, dict) else price
                if price is None:
                    missing.append("line_items.price")
                elif price != body["line_items[0][price]"]:
                    mismatched.append("line_items.price")
                if "quantity" not in row:
                    missing.append("line_items.quantity")
                elif type(row["quantity"]) is not int or row["quantity"] != 1:
                    mismatched.append("line_items.quantity")
    return not missing and not mismatched, missing, mismatched


def execute(name, args):
    key = client.require_key()  # Even dry runs and read-only calls enforce restricted keys.
    validate(name, args)
    if name == "stripe_whoami":
        account = client.request("GET", "/v1/account")
        return {"account_id": account["id"], "mode": "live" if key.startswith("rk_live_") else "test", "key_last4": key[-4:]}
    params = {"limit": 25}
    if "starting_after" in args:
        params["starting_after"] = args["starting_after"]
    lists = {"stripe_list_products": "products", "stripe_list_prices": "prices",
             "stripe_list_payment_links": "payment_links", "stripe_list_subscriptions": "subscriptions",
             "stripe_portal_config": "billing_portal/configurations"}
    if name in lists:
        if "product_id" in args:
            params["product"] = args["product_id"]
        if args.get("active_only"):
            params["active"] = "true"
        if "status" in args:
            params["status"] = args["status"]
        result = listing("/v1/" + lists[name], params)
        if name == "stripe_portal_config":
            result["exists"] = bool(result["data"])
        return result
    if name == "stripe_get_subscription":
        return project(client.request("GET", "/v1/subscriptions/" + args["id"]))
    if name == "stripe_create_product":
        path, body = "/v1/products", {k: args[k] for k in ("name", "description") if k in args}
    elif name == "stripe_create_price":
        path, body = "/v1/prices", {"product": args["product_id"], "unit_amount": args["amount_cents"], "currency": args["currency"]}
        if "interval" in args:
            body["recurring[interval]"] = args["interval"]
    elif name == "stripe_create_payment_link":
        path, body = "/v1/payment_links", {"line_items[0][price]": args["price_id"], "line_items[0][quantity]": 1}
        if "redirect_url" in args:
            body.update({"after_completion[type]": "redirect", "after_completion[redirect][url]": args["redirect_url"]})
    else:
        collection = "products" if name == "stripe_archive_product" else "prices" if name == "stripe_deactivate_price" else "payment_links"
        path, body = "/v1/" + collection + "/" + args["id"], {"active": "false"}
    if args.get("dry_run", True):
        return {"dry_run": True, "method": "POST", "path": path, "would_create_or_update": body,
                "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified."}
    created = client.request("POST", path, body)
    object_id = created.get("id")
    prefix = "prod" if path.startswith("/v1/products") else "price" if path.startswith("/v1/prices") else "plink"
    try:
        identifier(object_id, prefix)
    except client.StripeError:
        raise client.StripeError("Write returned no valid object ID; check Stripe Dashboard before retrying.") from None
    read_path = "/v1/" + ("products" if prefix == "prod" else "prices" if prefix == "price" else "payment_links") + "/" + object_id
    try:
        read_params = {"expand[]": "line_items"} if name == "stripe_create_payment_link" else None
        verified = client.request("GET", read_path, read_params)
        ok, missing, mismatched = verify_readback(verified, object_id, prefix, body)
        return {"id": object_id, "dry_run": False, "verified": ok, "object": project(verified),
                "unverifiable_fields": missing, "mismatched_fields": mismatched,
                "warning": None if ok else "Write accepted but readback did not establish the requested state; do not blindly retry."}
    except Exception:
        _, missing, _ = verify_readback({}, object_id, prefix, body)
        return {"id": object_id, "dry_run": False, "verified": False,
                "unverifiable_fields": missing,
                "warning": "Write accepted; readback failed. Check Dashboard before any retry."}


def handler(name):
    def call(args=None, **kwargs):
        try:
            return client.redact({"success": True, **execute(name, {} if args is None else args)})
        except client.StripeError as exc:
            return client.redact({"success": False, "error": str(exc),
                                  **({"error_details": exc.details} if exc.details else {})})
        except Exception:
            return client.redact({"success": False, "error": "Invalid input or unexpected response; no automatic retry. Check Stripe Dashboard before retrying a write."})
    return call
