"""Process-local exact-request references, not model-issued approval grants.

Native host consent is feature-detected at execution, never a generic policy
approval. No files, credentials, background workers or persistent grants here.
"""
from dataclasses import dataclass
import hashlib
import html
import json
import math
import secrets
import threading
import time
from urllib.parse import urlencode

from . import stripe_client as client

TTL_SECONDS = 300
MAX_PENDING = 256
# Includes escaped message, description, title and conservative native chrome.
# Conservative bound for the allowlisted native Telegram/Discord renderers
# only; other shipped surfaces can collapse or truncate well below this limit.
MAX_APPROVAL_DISPLAY = 750
NATIVE_CHROME_RESERVE = 300
WRITE_PLATFORMS = frozenset({"telegram", "discord"})
_lock = threading.Lock()
_pending = {}


@dataclass(frozen=True)
class Preview:
    preview_id: str
    tool: str
    arguments: tuple
    origin: str
    method: str
    path: str
    body: tuple
    encoded: bytes
    key_fingerprint: str
    mode: str
    context: tuple
    expires: float
    idempotency_key: str


def _session_platform():
    """Unusable host platform signals may preview, but can never authorize."""
    try:
        from tools.approval_context import _get_session_platform
        platform = _get_session_platform()
        return platform if type(platform) is str else None
    except Exception:
        return None


def context(session_id=None, task_id=None):
    """Host-owned context plus injected handler identity, where available."""
    for value in (session_id, task_id):
        if value is not None and (type(value) is not str or len(value) > 2000):
            raise client.StripeError("Invalid execution context.")
    try:
        from tools.approval_context import get_current_session_key
    except ImportError:
        session_key = None  # Standalone previews still work without Hermes.
    else:
        try:
            session_key = get_current_session_key()
            if type(session_key) is not str or not session_key:
                raise ValueError("invalid host context")
        except Exception:
            raise client.StripeError("Cannot establish native approval session context.") from None
    return (client.profile_home(), session_key, session_id, task_id, _session_platform())


def fingerprint(key):
    # Complete private fingerprint binds the key/account/mode, not just its last4.
    return hashlib.sha256(key.encode("ascii")).hexdigest()


def business_arguments(args):
    return tuple(sorted((k, v) for k, v in args.items() if k not in {"dry_run", "preview_id"}))


def _purge(now):
    for token in [token for token, pending in _pending.items() if now >= pending.expires]:
        del _pending[token]


def prepare(tool, args, path, body, key, execution_context):
    if args.get("preview_id") is not None:
        raise client.StripeError("A preview_id is only accepted with dry_run:false; request a new preview without it.")
    if client.ORIGIN != "https://api.stripe.com":
        raise client.StripeError("Stripe origin changed; refusing preview.")
    with _lock:
        now = time.monotonic()
        _purge(now)
        if len(_pending) >= MAX_PENDING:
            raise client.StripeError("Pending preview limit reached (256); wait for expiry before creating another.")
        token = secrets.token_urlsafe(32)
        while token in _pending:
            token = secrets.token_urlsafe(32)
        pending = Preview(token, tool, business_arguments(args), client.ORIGIN, "POST", path,
                          tuple(sorted(body.items())), urlencode(sorted(body.items())).encode("ascii"),
                          fingerprint(key), "live" if key.startswith("rk_live_") else "test",
                          execution_context, now + TTL_SECONDS, "stripe-preview-" + token)
        _pending[token] = pending
    return {"dry_run": True, "preview_id": token, "expires_in_seconds": TTL_SECONDS,
            "origin": pending.origin, "method": pending.method, "path": pending.path,
            "would_create_or_update": dict(pending.body), "encoded_form": pending.encoded.decode("ascii"),
            "idempotency_key": pending.idempotency_key,
            "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified. This reference is not approval; execution requires native one-operation human consent."}


def claim(tool, args, path, body, key, execution_context):
    token = args.get("preview_id")
    if not isinstance(token, str) or len(token) != 43:
        raise client.StripeError("Execution requires the original preview_id and matching arguments.")
    # Remove atomically BEFORE any prompt, including on mismatch. No retry grant
    # survives denial, cancellation, error or an uncertain transport outcome.
    with _lock:
        pending = _pending.pop(token, None)
        _purge(time.monotonic())
    if pending is None:
        raise client.StripeError("Unknown, expired or already consumed preview_id; no write attempted.")
    if time.monotonic() >= pending.expires:
        raise client.StripeError("Preview expired; no write attempted.")
    if (pending.tool != tool or pending.arguments != business_arguments(args)
            or pending.origin != client.ORIGIN or pending.origin != "https://api.stripe.com"
            or pending.method != "POST" or pending.path != path or pending.body != tuple(sorted(body.items()))
            or pending.key_fingerprint != fingerprint(key) or pending.context != execution_context):
        raise client.StripeError("Preview does not match request, restricted key or execution context; no write attempted.")
    return pending


def _human_available(execution_context):
    """Only allowlisted native gateways, never CLI/custom/delegated callbacks."""
    from tools.approval_context import _no_user_can_answer, _is_gateway_approval_context
    from tools.delegate_tool_registry import get_subagent_attribution
    if _no_user_can_answer() is not False or _is_gateway_approval_context() is not True:
        return False
    platform = _session_platform()
    if platform not in WRITE_PLATFORMS or platform != execution_context[4]:
        return False
    return not any(get_subagent_attribution(value) for value in execution_context[1:4] if value)


def _interrupted():
    from tools.interrupt import is_interrupted
    # Missing/incompatible interrupt API is caught by authorize: never assume safe.
    return is_interrupted() is not False


def recheck(pending, expected_key, session_id=None, task_id=None):
    """After approval, and again immediately before constructing the POST."""
    try:
        if (time.monotonic() >= pending.expires or _interrupted()
                or not _human_available(pending.context)
                or context(session_id, task_id) != pending.context
                or client.require_key() != expected_key
                or fingerprint(expected_key) != pending.key_fingerprint
                or client.ORIGIN != pending.origin):
            raise client.StripeError("Approval became stale (expiry, key, context or interrupt); preview consumed. No write attempted.")
    except client.StripeError:
        raise
    except Exception:
        raise client.StripeError("Cannot recheck native approval context; preview consumed. No write attempted.") from None


def authorize(pending, expected_key, session_id=None, task_id=None):
    """One native human consent call, never yolo/smart/allowlist policy.

    Internal MCP consent helper, not a public/stable Hermes plugin API. Host
    maps its one-call UI answer to accept/decline/cancel; remember_key=None
    offers no session/permanent scope and stores nothing. No model approve tool.
    """
    try:
        from tools.approval_prompt import request_elicitation_consent
        from agent.redact import redact_approval_display
        if _interrupted() or not _human_available(pending.context):
            raise client.StripeError("Writes require an interactive native Telegram or Discord gateway human approval channel; CLI/TUI and unverified platforms cannot execute.")
        remaining = pending.expires - time.monotonic()
        if remaining <= 0:
            raise client.StripeError("Preview expired before approval.")
        # Unique message prevents the host's identical-prompt coalescing. Form
        # data is serialized ASCII (including escaped control characters).
        message = (f"{pending.tool} preview={pending.preview_id}\n"
                   f"mode={pending.mode} key-sha256={pending.key_fingerprint[:12]}\n"
                   f"{pending.method} {pending.origin}{pending.path}\n"
                   f"form: {pending.encoded.decode('ascii')}")
        description = "One exact request; no saved consent."
        title = "Approve exact Stripe request once?"
        # Redact credential-shaped caller text before any host UI/hook sees it.
        safe_message, safe_description = json.loads(client.redact([message, description]))
        if (safe_message, safe_description) != (message, description):
            raise client.StripeError("Request contains secret-shaped text that cannot be shown exactly; no write attempted.")
        if (not message.isascii() or sum(len(html.escape(value)) for value in (message, description, title))
                + NATIVE_CHROME_RESERVE > MAX_APPROVAL_DISPLAY):
            raise client.StripeError("Exact request exceeds native human approval UI display limit (750 escaped ASCII characters including reserved UI space). Shorten fields and request a new preview; no write attempted.")
        # The host also masks non-Stripe provider tokens and sanitizes display
        # characters. A grant for its transformed display cannot authorize the
        # original bytes. Force the strongest gateway redaction regardless of
        # host settings; never disable it or reveal the tail.
        for value in (message, description, title):
            displayed = redact_approval_display(value, force=True)
            if type(displayed) is not str or displayed != value:
                raise client.StripeError("Native approval would mask or transform request details; exact visible consent is impossible. No write attempted.")
        decision = request_elicitation_consent(
            message, description, timeout_seconds=max(1, math.floor(remaining)),
            surface="stripe-commerce", title=title, remember_key=None)
        if type(decision) is not str or decision != "accept":
            raise client.StripeError("Native human approval denied, cancelled, timed out or unavailable; preview consumed. No write attempted.")
        recheck(pending, expected_key, session_id, task_id)
    except client.StripeError:
        raise
    except Exception:
        raise client.StripeError("Native one-operation human approval unavailable or incompatible; preview consumed. No write attempted.") from None
