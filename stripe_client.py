"""Bounded, single-origin Stripe transport; no SDK, proxy, redirects or retries."""
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = "https://api.stripe.com"
MAX_BYTES = 1024 * 1024
KEY_HELP = "STRIPE_API_KEY must be a restricted rk_test_ or rk_live_ key. Create a restricted key in Stripe Dashboard > Developers > API keys; never paste keys in chat."

class StripeError(Exception):
    pass


def require_key():
    key = os.environ.get("STRIPE_API_KEY", "")
    if not re.fullmatch(r"rk_(?:test|live)_[A-Za-z0-9]+", key):
        raise StripeError(KEY_HELP)
    return key


def redact(value):
    text = json.dumps(value, ensure_ascii=True)
    key = os.environ.get("STRIPE_API_KEY", "")
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"(?:rk|sk)_(?:test|live)_[A-Za-z0-9]+", "[REDACTED]", text)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StripeError("Stripe redirect refused; credentials never leave api.stripe.com.")


def request(method, path, params=None):
    key = require_key()  # Re-read on EVERY request, not just plugin load.
    read = r"/v1/(?:account|products(?:/prod_[A-Za-z0-9]+)?|prices(?:/price_[A-Za-z0-9]+)?|payment_links(?:/plink_[A-Za-z0-9]+)?|subscriptions(?:/sub_[A-Za-z0-9]+)?|billing_portal/configurations)"
    write = r"/v1/(?:products(?:/prod_[A-Za-z0-9]+)?|prices(?:/price_[A-Za-z0-9]+)?|payment_links(?:/plink_[A-Za-z0-9]+)?)"
    if not ((method == "GET" and re.fullmatch(read, path)) or
            (method == "POST" and re.fullmatch(write, path))):
        raise StripeError("Operation outside the catalog/read-only allowlist.")
    encoded = urllib.parse.urlencode(params or {}).encode("utf-8")
    url = ORIGIN + path
    if method == "GET" and encoded:
        url += "?" + encoded.decode("ascii")
    req = urllib.request.Request(url, data=encoded if method == "POST" else None,
        method=method, headers={"Authorization": "Bearer " + key,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "stripe-commerce-hermes/0.1.0"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=20) as response:
            if urllib.parse.urlsplit(response.geturl()).netloc != "api.stripe.com" or not response.geturl().startswith(ORIGIN + "/"):
                raise StripeError("Unexpected response origin.")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise StripeError("Stripe response exceeds 1 MiB limit.")
            result = json.loads(body)
            if not isinstance(result, dict) or "error" in result:
                raise StripeError("Unexpected Stripe response.")
            return result
    except urllib.error.HTTPError as exc:
        # Do not echo response bodies, URLs, headers, or arbitrary exception text.
        if exc.code in (401, 403):
            raise StripeError("Stripe authorization denied (HTTP %s); check restricted-key permissions and mode." % exc.code) from None
        raise StripeError("Stripe HTTP %s; no automatic retry. Check Dashboard before retrying a write." % exc.code) from None
    except StripeError:
        raise
    except Exception:
        raise StripeError("Stripe network or response failure; no automatic retry. Check Dashboard before retrying a write.") from None
