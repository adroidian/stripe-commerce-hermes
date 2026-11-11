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
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def configured_key():
    """Use the active profile scope; never fall back after a resolver error."""
    try:
        from agent.secret_scope import get_secret
    except ModuleNotFoundError as exc:
        if exc.name != "agent":
            raise StripeError("Hermes profile credential resolver unavailable.") from None
        # Standalone unit tests/offline demos, not multiplexed Hermes execution.
        key = os.environ.get("STRIPE_API_KEY", "")
    except Exception:
        raise StripeError("Hermes profile credential resolver incompatible.") from None
    else:
        try:
            key = get_secret("STRIPE_API_KEY")
        except Exception:
            raise StripeError("Cannot resolve STRIPE_API_KEY for the active Hermes profile.") from None
    if key is None:
        return ""
    if type(key) is not str:
        raise StripeError(KEY_HELP)
    return key


def profile_home():
    try:
        from hermes_constants import get_hermes_home
    except ModuleNotFoundError as exc:
        if exc.name == "hermes_constants":
            return None  # Standalone preview; no Hermes profile is present.
        raise StripeError("Hermes profile context unavailable.") from None
    except Exception:
        raise StripeError("Hermes profile context incompatible.") from None
    try:
        home = get_hermes_home()
        if not isinstance(home, (str, os.PathLike)) or not str(home):
            raise ValueError("invalid profile home")
        return str(home)
    except Exception:
        raise StripeError("Cannot resolve active Hermes profile context.") from None


def require_key():
    key = configured_key()
    if not re.fullmatch(r"rk_(?:test|live)_[A-Za-z0-9]+", key):
        raise StripeError(KEY_HELP)
    return key


def redact(value):
    text = json.dumps(value, ensure_ascii=True)
    try:
        key = configured_key()
    except StripeError:
        key = ""  # Do not fall back to another profile's process environment.
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"(?:rk|sk)_(?:test|live)_[A-Za-z0-9]+", "[REDACTED]", text)


def error_details(response):
    """Bounded machine-readable diagnostics, never Stripe's free-form messages."""
    details = {}
    try:
        body = response.read(MAX_BYTES + 1)
        raw = json.loads(body) if len(body) <= MAX_BYTES else None
        error = raw.get("error") if isinstance(raw, dict) else None
        if isinstance(error, dict):
            for field in ("type", "code", "param"):
                value = error.get(field)
                # Stripe codes/types and bracketed parameter names only. Drop,
                # rather than truncate, oversized values or credential-shaped tokens.
                if (isinstance(value, str) and 1 <= len(value) <= 128
                        and re.fullmatch(r"[A-Za-z0-9_\[\]]+", value)
                        and json.loads(redact(value)) == value):
                    details[field] = value
    except Exception:
        pass  # Invalid JSON, oversized or unreadable body: generic fallback.
    try:
        retry = response.headers.get("Retry-After")
        if isinstance(retry, str) and len(retry) <= 64 and re.fullmatch(r"-?[0-9]+", retry):
            details["retry_after_seconds"] = max(0, min(3600, int(retry)))
    except Exception:
        pass
    return details


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StripeError("Stripe redirect refused; credentials never leave api.stripe.com.")


def request(method, path, params=None, *, encoded_body=None, expected_key=None, idempotency_key=None, before_send=None):
    key = require_key()  # Re-read on EVERY request, not just plugin load.
    read = r"/v1/(?:account|products(?:/prod_[A-Za-z0-9]+)?|prices(?:/price_[A-Za-z0-9]+)?|payment_links(?:/plink_[A-Za-z0-9]+)?|subscriptions(?:/sub_[A-Za-z0-9]+)?|billing_portal/configurations)"
    write = r"/v1/(?:products(?:/prod_[A-Za-z0-9]+)?|prices(?:/price_[A-Za-z0-9]+)?|payment_links(?:/plink_[A-Za-z0-9]+)?)"
    if not ((method == "GET" and re.fullmatch(read, path)) or
            (method == "POST" and re.fullmatch(write, path))):
        raise StripeError("Operation outside the catalog/read-only allowlist.")
    if ORIGIN != "https://api.stripe.com":
        raise StripeError("Stripe origin changed; request refused.")
    if method == "POST":
        if (type(encoded_body) is not bytes or params is not None or expected_key != key
                or not callable(before_send) or not isinstance(idempotency_key, str)
                or not re.fullmatch(r"stripe-preview-[A-Za-z0-9_-]{43}", idempotency_key)):
            raise StripeError("POST requires captured preview bytes, matching expected key and idempotency key.")
        encoded = encoded_body  # NEVER serialize mutable caller arguments after approval.
        key = expected_key
    else:
        if encoded_body is not None or expected_key is not None or idempotency_key is not None or before_send is not None:
            raise StripeError("Preview write parameters are invalid for read requests.")
        encoded = urllib.parse.urlencode(params or {}).encode("utf-8")
    url = ORIGIN + path
    if method == "GET" and encoded:
        url += "?" + encoded.decode("ascii")
    headers = {"Authorization": "Bearer " + key,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "stripe-commerce-hermes/0.2.0"}
    if method == "POST":
        headers["Idempotency-Key"] = idempotency_key
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    if method == "POST":
        before_send()  # Local expiry/key/scope/request after opener/SSL-context setup, before network I/O (not Stop).
    # Opener/TLS construction can yield to another context. Check again before
    # constructing the request, but send the CAPTURED key, not a rotated value.
    if method == "POST" and require_key() != expected_key:
        raise StripeError("Restricted key rotated after approval; no write attempted.")
    req = urllib.request.Request(url, data=encoded if method == "POST" else None,
                                 method=method, headers=headers)
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
        details = error_details(exc)
        exc.close()
        if exc.code in (401, 403):
            raise StripeError("Stripe authorization denied (HTTP %s); check restricted-key permissions and mode." % exc.code, details) from None
        raise StripeError("Stripe HTTP %s; no automatic retry. Check Dashboard before retrying a write." % exc.code, details) from None
    except StripeError:
        raise
    except Exception:
        raise StripeError("Stripe network or response failure; no automatic retry. Check Dashboard before retrying a write.") from None
