import asyncio
import os

import pytest

# app.main loads settings at import time; provide harmless test-only defaults.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app.main import keep_typing


class FakeBot:
    def __init__(self):
        self.calls = []
        self.first_call = asyncio.Event()

    async def send_chat_action(self, *, chat_id, action):
        self.calls.append((chat_id, action))
        self.first_call.set()


@pytest.mark.asyncio
async def test_keep_typing_sends_typing_action_immediately():
    bot = FakeBot()
    task = asyncio.create_task(keep_typing(bot, 12345))

    try:
        await asyncio.wait_for(bot.first_call.wait(), timeout=1)
        assert bot.calls == [(12345, "typing")]
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_keep_typing_can_be_cancelled_cleanly():
    bot = FakeBot()
    task = asyncio.create_task(keep_typing(bot, 67890))
    await asyncio.wait_for(bot.first_call.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert bot.calls[0][0] == 67890
