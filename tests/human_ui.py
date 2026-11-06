"""Test-only host UI contract doubles. Never imported by the plugin itself."""
import os
import sys
import threading
import types
from unittest.mock import Mock, patch


class HumanUI:
    def __init__(self):
        self.session_key = "human-session"
        self.platform = "telegram"
        self.profile_home = "/unit-test/profile-A"
        self.scope_key = None
        self.no_user = False
        self.interrupted = False
        self.delegated = False
        self.callback = Mock(return_value="once")
        self.notify = Mock()
        self.callbacks = {}
        self.gateway()
        self.prompt = Mock(side_effect=lambda command, description, **kw: self.callback(
            command, description, allow_permanent=kw["allow_permanent"], allow_session=kw["allow_session"]))
        self.wait = Mock(return_value={"resolved": True, "choice": "once"})
        self.consent = Mock(side_effect=self._consent)
        self.secret = Mock(side_effect=lambda name: os.environ.get(name, "") if self.scope_key is None else self.scope_key)
        self.policy = Mock(side_effect=AssertionError("Generic policy must never authorize a Stripe write"))
        self.display = Mock(side_effect=lambda text, **kw: text)
        modules = {}
        def module(name, **attrs):
            mod = types.ModuleType(name)
            mod.__dict__.update(attrs)
            modules[name] = mod
            return mod
        pkg = module("tools", __path__=[])
        module("tools.approval", _lock=threading.RLock(), _gateway_notify_cbs=self.callbacks,
               request_tool_approval=self.policy, is_auto_approve_active=Mock(return_value=True))
        module("tools.approval_context", get_current_session_key=lambda: self.session_key,
               _get_session_platform=lambda: self.platform,
               _no_user_can_answer=lambda: self.no_user,
               _is_gateway_approval_context=lambda: self.session_key in self.callbacks)
        module("tools.approval_gateway_wait", _await_gateway_decision=self.wait)
        module("tools.approval_prompt", request_elicitation_consent=self.consent, prompt_dangerous_approval=self.prompt)
        module("tools.terminal_tool", _get_approval_callback=lambda: self.callback)
        module("tools.interrupt", is_interrupted=lambda: self.interrupted)
        module("tools.delegate_tool_registry", get_subagent_attribution=lambda task_id: {"subagent_id": task_id} if self.delegated else None)
        for name, mod in list(modules.items()):
            if name != "tools":
                setattr(pkg, name.split(".")[-1], mod)
        agent = module("agent", __path__=[])
        agent.secret_scope = module("agent.secret_scope", get_secret=self.secret)
        agent.redact = module("agent.redact", redact_approval_display=self.display)
        module("hermes_constants", get_hermes_home=lambda: self.profile_home)
        self.modules = modules

    def _consent(self, message, description, *, timeout_seconds=None, surface=None, title=None, remember_key=None):
        # Model the internal native helper's documented return contract only;
        # parent integration exercises the REAL host bridge and formatter.
        assert remember_key is None
        if self.session_key in self.callbacks:
            decision = self.wait(self.session_key, self.notify, {
                "command": message, "description": description, "pattern_key": "mcp_elicitation",
                "pattern_keys": ["mcp_elicitation"], "allow_session": False, "allow_permanent": False}, surface=surface)
            if (type(decision) is not dict or decision.get("resolved") is not True
                    or decision.get("cancelled") or decision.get("notify_failed")):
                return "cancel"
            choice = decision.get("choice")
        else:
            choice = self.prompt(message, description, timeout_seconds=timeout_seconds,
                                 allow_permanent=False, allow_session=False, approval_callback=self.callback, title=title)
        # Native helper treats legacy scope choices as one call with no remember_key.
        return "accept" if type(choice) is str and choice in {"once", "session", "always"} else "decline"

    def start(self):
        self.patch = patch.dict(sys.modules, self.modules)
        self.patch.start()
        return self

    def stop(self):
        self.patch.stop()

    def gateway(self):
        self.callbacks[self.session_key] = self.notify

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()
