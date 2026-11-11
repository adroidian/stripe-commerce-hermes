"""Offline native host fixture: real registration/dispatcher/gate/queue/handlers.

Only delivery/human answers and Stripe HTTP are simulated. Run with Hermes on
PYTHONPATH and a disposable, credential-cleared HOME (see VALIDATION).
"""
import itertools
import json
import os
import sys
from contextlib import ExitStack
from unittest.mock import Mock, patch


class HumanUI:
    def __init__(self):
        self.platform = "telegram"
        self.session_key = "native-test-route"
        self.notify = Mock(side_effect=self._answer)
        self.choice = "once"
        self.on_prompt = None
        self.counter = itertools.count()
        self.stack = ExitStack()

    def _answer(self, data):
        from tools import approval
        if self.on_prompt:
            self.on_prompt(data)
        if self.choice == "unavailable":
            raise RuntimeError("simulated delivery failure")
        if self.choice == "cancelled":
            approval.unregister_gateway_notify(self.session_key)
        else:
            approval.resolve_gateway_approval(self.session_key, self.choice, request_id=data["request_id"])

    def start(self):
        from hermes_cli import plugins
        import model_tools
        from tools import approval
        self.model_tools = model_tools
        self.approval = approval
        self.manager = plugins.PluginManager()
        self.manager._discovered = True
        self.stack.enter_context(patch.object(plugins, "get_plugin_manager", return_value=self.manager))
        self.ctx = plugins.PluginContext(plugins.PluginManifest(name="stripe-commerce", source="test"), self.manager)
        plugin = sys.modules["stripe_commerce"]
        plugin.write_approval._pending.clear()
        if hasattr(plugin.write_approval, "_attempts"):
            plugin.write_approval._attempts.clear()
        if hasattr(plugin.write_approval, "_reservations"):
            plugin.write_approval._reservations.clear()
        plugin.register(self.ctx)
        approval.register_gateway_notify(self.session_key, self.notify)
        return self

    def stop(self):
        self.approval.unregister_gateway_notify(self.session_key)
        self.manager.unload()
        self.stack.close()

    def dispatch(self, name, args, **kwargs):
        from tools import approval_context
        env = {"HERMES_SESSION_PLATFORM": self.platform, "HERMES_INTERACTIVE": "",
               "HERMES_CRON_SESSION": "", "HERMES_SINGLE_QUERY_SESSION": ""}
        env.update(kwargs.pop("env", {}))
        ids = {"session_id": "session-A", "task_id": "task-A", "turn_id": "turn-A",
               "tool_call_id": "call-" + str(next(self.counter)), "api_request_id": "request-A"}
        ids.update(kwargs)
        with patch.dict(os.environ, env):
            token = approval_context.set_current_session_key(self.session_key)
            try:
                return self.model_tools.handle_function_call(name, args, **ids)
            finally:
                approval_context.reset_current_session_key(token)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()
