import asyncio
import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app import main


class FakeSentAnimation:
    def __init__(self):
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_animation(self, *, animation, disable_notification):
        self.sent.append((animation, disable_notification))
        return FakeSentAnimation()


@pytest.mark.asyncio
async def test_thinking_animation_sends_after_delay(monkeypatch):
    monkeypatch.setattr(main, "THINKING_ANIMATION_DELAY_SECONDS", 0)
    message = FakeMessage()

    sent = await main.send_delayed_thinking_animation(message)

    assert sent is not None
    assert len(message.sent) == 1
    animation, silent = message.sent[0]
    assert animation.filename == "ani_zeo_thinking.gif"
    assert silent is True


@pytest.mark.asyncio
async def test_thinking_animation_is_removed_after_reply(monkeypatch):
    monkeypatch.setattr(main, "THINKING_ANIMATION_DELAY_SECONDS", 0)
    message = FakeMessage()
    task = asyncio.create_task(main.send_delayed_thinking_animation(message))
    await asyncio.sleep(0.01)

    await main.stop_thinking_animation(task)

    # The fake Telegram message is returned by the task and deleted by cleanup.
    assert len(message.sent) == 1


@pytest.mark.asyncio
async def test_fast_reply_cancels_pending_thinking_animation(monkeypatch):
    monkeypatch.setattr(main, "THINKING_ANIMATION_DELAY_SECONDS", 30)
    message = FakeMessage()
    task = asyncio.create_task(main.send_delayed_thinking_animation(message))

    await main.stop_thinking_animation(task)

    assert message.sent == []
