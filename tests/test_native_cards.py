"""Real Telegram/Discord native card builders with installed SDK objects.
No renderer doubles: only outbound prompt delivery and the human answer mocked.
These are serialization checks, not live client/human qualification.
"""
import asyncio
import html
from types import SimpleNamespace
import pytest
from .test_preview_binding import c, MUTATIONS

class OfflineLoop(asyncio.SelectorEventLoop):
    # asyncio's wakeup socketpair is unnecessary: every coroutine here is local
    # and runs synchronously. Keep the global socket-denial assertion active.
    def _make_self_pipe(self):
        self._ssock = self._csock = None
    def _close_self_pipe(self): pass

@pytest.mark.parametrize("platform", ["telegram", "discord"])
@pytest.mark.parametrize("name", [*MUTATIONS, "boundary_product"])
def test_native_card_complete_canonical_projection(c, platform, name):
    from gateway.platforms.base import SendResult
    from plugins.platforms.telegram.adapter import TelegramAdapter
    from plugins.platforms.discord.adapter import DiscordAdapter
    captured = []
    c.ui.platform = platform
    args = MUTATIONS.get(name)
    boundary = name == "boundary_product"
    if boundary:
        name = "stripe_create_product"
        seed = c.preview(name, {"name": "X"})
        frozen = c.binding._pending[seed["preview_id"]]
        overhead = len(html.escape(c.binding.request_message(frozen))) - 1
        args = {"name": "A" * (300 - overhead)}
    async def render(data):
        cls = TelegramAdapter if platform == "telegram" else DiscordAdapter
        adapter = cls.__new__(cls)
        if platform == "telegram":
            adapter._approval_state = {}; adapter._reply_to_mode = "off"
            async def delivery(operation, chat_id, metadata, build, **kw):
                text, keyboard, on_sent = build()
                assert data["command"] in html.unescape(text)
                assert data["description"] in html.unescape(text)
                assert len(text) <= 4096
                rows = keyboard.to_dict()["inline_keyboard"]
                choices = [b["callback_data"].split(":")[1] for row in rows for b in row]
                assert choices == ["once", "deny"]
                captured.append(text)
                return SendResult(success=True, message_id="mock")
        else:
            adapter.config = SimpleNamespace(extra={})
            adapter._allowed_user_ids = set(); adapter._allowed_role_ids = set()
            adapter._approval_mention_content = lambda: ""
            async def delivery(chat_id, metadata, build):
                payload, view = build(None)
                assert data["command"] in payload["content"]
                assert data["description"] in payload["content"]
                assert len(payload["content"]) <= 2000
                assert len(view.children) == 2
                assert len(view.to_components()[0]["components"]) == 2
                assert payload["embed"].to_dict()["title"]
                captured.append(payload["content"])
                view.stop()
                return SendResult(success=True, message_id="mock")
        adapter._send_prompt = delivery
        return await adapter.send_exec_approval("test-chat", data["command"], c.ui.session_key,
            description=data["description"], allow_session=data["allow_session"], allow_permanent=data["allow_permanent"])
    def notify(data):
        loop = OfflineLoop()
        try: assert loop.run_until_complete(render(data)).success
        finally: loop.close()
        c.ui._answer(data)
    c.ui.notify.side_effect = notify
    p = c.preview(name, args); c.responses(name, args)
    result = c.live(name, args, p)
    assert result["success"] and result["verified"], result
    assert len(captured) == 1
    assert c.open.call_args_list[0].args[0].data == p["encoded_form"].encode("ascii")
    if boundary:
        assert len(html.escape(c.ui.notify.call_args.args[0]["description"])) == 300
        c.open.reset_mock(); c.ui.notify.reset_mock()
        overflow = {"name": args["name"] + "A"}
        c.blocked(c.live(name, overflow)); c.ui.notify.assert_not_called()
