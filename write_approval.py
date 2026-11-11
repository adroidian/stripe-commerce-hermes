"""Public mandatory approval: frozen previews, observed display, dynamic leases.

Observers record facts, not vetoes. Only normal post-gate execution middleware
can mint a one-use handler lease. No private approval/context/interrupt APIs.
After fresh Once and host admission for execution, Stop cannot guarantee abort
of that approved operation (including during TLS setup).
"""
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import html
import json
import secrets
import threading
import time
from urllib.parse import urlencode

from . import stripe_client as client

TTL_SECONDS = 300
MAX_PENDING = 256
# Discord's native reason budget is 300; command room is dynamic. Telegram has
# more room. Measure escaped ASCII conservatively, including both projections.
MAX_DESCRIPTION = 300
MAX_COMMAND = 1000
MAX_APPROVAL_DISPLAY = 1800
NATIVE_CHROME_RESERVE = 500
WRITE_PLATFORMS = frozenset({"telegram", "discord"})
LIFECYCLE_HOOKS = ("agent_loop_stopped", "on_session_reset", "on_session_finalize", "on_session_end", "on_session_delete")
_lock = threading.RLock()
_pending = {}
_attempts = {}
_reservations = {}
_generation = 0
_surface = lambda: None
_lease: ContextVar["Lease | None"] = ContextVar("stripe_commerce_execution_lease", default=None)


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


@dataclass
class Attempt:
    preview: Preview
    ids: tuple
    rule: str
    command: str
    message: str
    pre: tuple | None = None
    approved: bool = False
    invalid: bool = False


@dataclass
class Lease:
    attempt: Attempt
    consumed: bool = False
    active: bool = True


def install(ctx):
    global _surface
    _surface = getattr(ctx, "session_surface", lambda: None)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", retire_attempt)
    ctx.register_hook("pre_approval_request", pre_approval_request)
    ctx.register_hook("post_approval_response", post_approval_response)
    ctx.register_middleware("tool_execution", execution_middleware)
    for hook in LIFECYCLE_HOOKS:
        ctx.register_hook(hook, invalidate)


def _session_platform():
    try:
        value = _surface()
        return value if type(value) is str else None
    except Exception:
        return None


def context(session_id=None, task_id=None):
    values = []
    for value in (session_id, task_id):
        if value is not None and (type(value) is not str or len(value) > 2000):
            raise client.StripeError("Invalid execution context.")
        values.append(value or "")  # Host hooks use empty string; handlers use None.
    return (client.profile_home(), *values, _session_platform())


def fingerprint(key):
    return hashlib.sha256(key.encode("ascii")).hexdigest()


def business_arguments(args):
    return tuple(sorted((k, v) for k, v in args.items() if k not in {"dry_run", "preview_id"}))


def _purge(now):
    for token in [k for k, p in _pending.items() if now >= p.expires]:
        del _pending[token]
    for rule in [k for k, a in _attempts.items() if now >= a.preview.expires]:
        del _attempts[rule]
    for token in [k for k, p in _reservations.items() if now >= p.expires]:
        del _reservations[token]


def prepare(tool, args, path, body, key, execution_context):
    if args.get("preview_id") is not None:
        raise client.StripeError("A preview_id is only accepted with dry_run:false; request a new preview without it.")
    if client.ORIGIN != "https://api.stripe.com":
        raise client.StripeError("Stripe origin changed; refusing preview.")
    with _lock:
        now = time.monotonic()
        _purge(now)
        if len(_pending) + len(_attempts) + len(_reservations) >= MAX_PENDING:
            raise client.StripeError("Pending preview limit reached (256); wait for expiry before creating another.")
        token = secrets.token_urlsafe(32)
        while token in _pending or token in _reservations or any(a.preview.preview_id == token for a in _attempts.values()):
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


def match(pending, tool, args, path, body, key, execution_context):
    if time.monotonic() >= pending.expires:
        raise client.StripeError("Preview expired; no write attempted.")
    if (pending.tool != tool or pending.preview_id != args.get("preview_id") or args.get("dry_run") is not False
            or pending.arguments != business_arguments(args)
            or pending.origin != client.ORIGIN or pending.origin != "https://api.stripe.com"
            or pending.method != "POST" or pending.path != path or pending.body != tuple(sorted(body.items()))
            or pending.encoded != urlencode(sorted(body.items())).encode("ascii")
            or pending.key_fingerprint != fingerprint(key)
            or pending.mode != ("live" if key.startswith("rk_live_") else "test")
            or pending.context != execution_context):
        raise client.StripeError("Preview does not match request, restricted key or execution context; no write attempted.")


def _ids(kwargs):
    return tuple(kwargs.get(k) or "" for k in ("session_id", "task_id", "turn_id", "tool_call_id", "api_request_id"))


def _supported():
    try:
        from hermes_cli.plugins import VALID_TOOL_APPROVAL_POLICIES
        return (isinstance(VALID_TOOL_APPROVAL_POLICIES, (set, frozenset))
                and "mandatory" in VALID_TOOL_APPROVAL_POLICIES)
    except Exception:
        return False


def request_message(pending):
    # The host's independently checked command supplies tool + unique preview ID
    # and all business args. Do not duplicate those in Discord's 300-char reason.
    return (f"{pending.mode} key-sha256={pending.key_fingerprint[:12]}\n"
            f"{pending.method} {pending.origin}{pending.path}\n"
            f"form: {pending.encoded.decode('ascii')}")


def pre_tool_call(tool_name, args, **kwargs):
    from .tools import SPECS, validate, request_spec
    if tool_name not in SPECS or "dry_run" not in SPECS[tool_name][1] or not isinstance(args, dict) or args.get("dry_run", True) is not False:
        return None
    pending = None
    try:
        # Reserve BEFORE validation/capability checks/approve. Even a bad or
        # unsupported execution attempt consumes the referenced preview.
        with _lock:
            generation = _generation
            pending = _pending.pop(args.get("preview_id"), None) if type(args.get("preview_id")) is str else None
            _purge(time.monotonic())
            if pending is not None:
                _reservations[pending.preview_id] = pending
        if pending is None:
            raise client.StripeError("Unknown, expired or already consumed preview_id; no write attempted.")
        validate(tool_name, args)
        key = client.require_key()
        path, body = request_spec(tool_name, args)
        match(pending, tool_name, args, path, body, key, context(kwargs.get("session_id"), kwargs.get("task_id")))
        ids = _ids(kwargs)
        if (not _supported() or pending.context[3] not in WRITE_PLATFORMS
                or not pending.context[0] or not ids[0] or not ids[2] or not ids[3]):
            raise client.StripeError("Writes require public mandatory approval support and a native Telegram/Discord session; reads and previews remain available.")
        command = json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False, allow_nan=False)
        message = request_message(pending)
        # Ordinary URL form encoding is the actual wire projection, never a
        # secret escape hatch: the raw args command must independently match
        # the host-redacted command in the observers below.
        if json.loads(client.redact([command, message])) != [command, message]:
            raise client.StripeError("Request contains secret-shaped text; exact approval unavailable.")
        if (not command.isascii() or not message.isascii()
                or any(ord(c) < 32 and c != "\n" for c in message)
                or "`" in command or "`" in message
                or len(html.escape(message)) > MAX_DESCRIPTION
                or len(html.escape(command)) > MAX_COMMAND
                or len(html.escape(command)) + len(html.escape(message)) + NATIVE_CHROME_RESERVE > MAX_APPROVAL_DISPLAY):
            raise client.StripeError("Exact request exceeds native approval display limit or safe character set; shorten fields and request a new preview.")
        rule = "stripe-commerce:" + secrets.token_urlsafe(24)
        attempt = Attempt(pending, ids, rule, command, message)
        with _lock:
            if (time.monotonic() >= pending.expires or generation != _generation
                    or pending.preview_id not in _reservations):
                raise client.StripeError("Preview expired or invalidated before approval.")
            del _reservations[pending.preview_id]
            _attempts[rule] = attempt
        return {"action": "approve", "message": message, "rule_key": rule, "approval_policy": "mandatory"}
    except client.StripeError as exc:
        return {"action": "block", "message": str(exc)}
    except Exception:
        return {"action": "block", "message": "Cannot bind exact public mandatory approval; preview consumed. No write attempted."}
    finally:
        if pending is not None:
            with _lock:
                _reservations.pop(pending.preview_id, None)


def _observe(post, **kwargs):
    rule = kwargs.get("pattern_key", "")
    if not isinstance(rule, str) or not rule.startswith("plugin_rule:stripe-commerce:"):
        return
    with _lock:
        _purge(time.monotonic())
        attempt = _attempts.get(rule.removeprefix("plugin_rule:"))
        if attempt is None:
            return
        observed = (kwargs.get("command"), kwargs.get("description"), kwargs.get("session_key"), kwargs.get("surface"),
                    kwargs.get("session_id"), kwargs.get("turn_id"), kwargs.get("tool_call_id"))
        exact = (kwargs.get("command") == attempt.command and kwargs.get("description") == attempt.message
                 and kwargs.get("pattern_keys") == [rule] and kwargs.get("surface") == "gateway"
                 and type(kwargs.get("session_key")) is str and bool(kwargs.get("session_key"))
                 and (kwargs.get("session_id"), kwargs.get("turn_id"), kwargs.get("tool_call_id"))
                 == (attempt.ids[0], attempt.ids[2], attempt.ids[3])
                 and not kwargs.get("coalesced") and not kwargs.get("cancelled"))
        if not exact or attempt.invalid or (not post and attempt.pre is not None):
            attempt.invalid = True
        elif post:
            if attempt.pre != observed or attempt.approved or kwargs.get("choice") != "once":
                attempt.invalid = True
            else:
                attempt.approved = True
        else:
            attempt.pre = observed


def pre_approval_request(**kwargs):
    _observe(False, **kwargs)


def post_approval_response(**kwargs):
    _observe(True, **kwargs)


def retire_attempt(**kwargs):
    """No unused observer record survives a completed/blocked host dispatch."""
    ids = _ids(kwargs)
    with _lock:
        for rule in [k for k, a in _attempts.items() if a.ids == ids]:
            del _attempts[rule]


def execution_middleware(tool_name, args, next_call, **kwargs):
    from .tools import SPECS
    if tool_name not in SPECS or "dry_run" not in SPECS[tool_name][1] or not isinstance(args, dict) or args.get("dry_run", True) is not False:
        return next_call(args)
    with _lock:
        _purge(time.monotonic())
        matches = [a for a in _attempts.values() if a.ids == _ids(kwargs) and a.preview.preview_id == args.get("preview_id")]
        for a in matches:
            del _attempts[a.rule]
        if len(matches) != 1 or matches[0].invalid or not matches[0].approved or matches[0].pre is None:
            return client.redact({"success": False, "error": "Missing exact native fresh-once approval evidence; no write attempted."})
        lease = Lease(matches[0])
    token = _lease.set(lease)
    try:
        return next_call(args)
    finally:
        lease.active = False  # Copied contexts cannot retain a live lease.
        _lease.reset(token)


def claim(tool, args, path, body, key, execution_context):
    lease = _lease.get()
    with _lock:
        if lease is None or not lease.active or lease.consumed:
            raise client.StripeError("Execution requires a normal post-gate one-use handler lease; no write attempted.")
        lease.consumed = True
    pending = lease.attempt.preview
    match(pending, tool, args, path, body, key, execution_context)
    return pending


def recheck(pending, expected_key, session_id=None, task_id=None):
    """Local binding check after opener/SSL-context setup; NOT a Stop guarantee."""
    if (time.monotonic() >= pending.expires
            or context(session_id, task_id) != pending.context
            or client.require_key() != expected_key
            or fingerprint(expected_key) != pending.key_fingerprint
            or client.ORIGIN != pending.origin or pending.origin != "https://api.stripe.com"
            or pending.method != "POST"
            or urlencode(sorted(pending.body)).encode("ascii") != pending.encoded):
        raise client.StripeError("Approval became stale (expiry, key, profile, session, task, surface or request); preview consumed. No write attempted.")


def invalidate(session_id="", **kwargs):
    # No reliable session identity means conservatively retire all pending state.
    global _generation
    with _lock:
        _generation += 1
        for token in [k for k, p in _pending.items() if not session_id or p.context[1] == session_id]:
            del _pending[token]
        for token in [k for k, p in _reservations.items() if not session_id or p.context[1] == session_id]:
            del _reservations[token]
        for rule in [k for k, a in _attempts.items() if not session_id or a.ids[0] == session_id]:
            del _attempts[rule]
