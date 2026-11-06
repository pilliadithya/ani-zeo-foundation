import asyncio
import os
import uuid

import httpx
import pytest

# app.main creates Settings at import time; provide harmless test-only values.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://unused")

from app import main as main_module


class FakeDatabase:
    def __init__(self, duplicate=False):
        self.claim_token = None if duplicate else uuid.uuid4()
        self.claim_calls = []
        self.completed = []
        self.failed = []

    async def claim_telegram_update(self, update_id):
        self.claim_calls.append(update_id)
        return self.claim_token

    async def complete_telegram_update(self, update_id, claim_token):
        self.completed.append((update_id, claim_token))

    async def fail_telegram_update(self, update_id, claim_token, label):
        self.failed.append((update_id, claim_token, label))


class FakeTelegramApp:
    def __init__(self, outcome="success"):
        self.bot = object()
        self.bot_data = {}
        self.outcome = outcome
        self.processed = []

    async def process_update(self, update):
        self.processed.append(update.update_id)
        if self.outcome == "raise":
            raise RuntimeError("test failure")
        if self.outcome == "handler_error":
            self.bot_data.setdefault("failed_update_ids", set()).add(update.update_id)
        if self.outcome == "timeout":
            await asyncio.sleep(1)


async def post_update(app, payload=None, secret="test-webhook-secret", headers=None):
    app.state.db = app.test_db
    app.state.telegram_app = app.test_telegram_app
    request_headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
    request_headers.update(headers or {})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/telegram/webhook",
            json=payload if payload is not None else {"update_id": 7001},
            headers=request_headers,
        )


@pytest.fixture
def configured_app(monkeypatch):
    monkeypatch.setattr(main_module.settings, "webhook_secret", "test-webhook-secret")
    return main_module.app


@pytest.mark.asyncio
async def test_webhook_completes_successful_update(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp()

    response = await post_update(configured_app)

    assert response.status_code == 200
    assert configured_app.test_telegram_app.processed == [7001]
    assert configured_app.test_db.completed[0][0] == 7001
    assert configured_app.test_db.failed == []


@pytest.mark.asyncio
async def test_webhook_ignores_duplicate_without_dispatch(configured_app):
    configured_app.test_db = FakeDatabase(duplicate=True)
    configured_app.test_telegram_app = FakeTelegramApp()

    response = await post_update(configured_app)

    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert configured_app.test_telegram_app.processed == []
    assert configured_app.test_db.completed == []


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp()

    response = await post_update(configured_app, secret="wrong")

    assert response.status_code == 403
    assert configured_app.test_db.claim_calls == []


@pytest.mark.asyncio
async def test_webhook_rejects_non_object_json(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp()

    response = await post_update(configured_app, payload=["not", "an", "update"])

    assert response.status_code == 400
    assert configured_app.test_db.claim_calls == []


@pytest.mark.asyncio
async def test_webhook_rejects_declared_oversized_body(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp()

    response = await post_update(
        configured_app,
        headers={"Content-Length": str(main_module.MAX_WEBHOOK_BODY_BYTES + 1)},
    )

    assert response.status_code == 413
    assert configured_app.test_db.claim_calls == []


@pytest.mark.asyncio
async def test_webhook_marks_dispatch_exception_failed(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp(outcome="raise")

    response = await post_update(configured_app)

    assert response.status_code == 500
    assert configured_app.test_db.failed[0][0] == 7001
    assert configured_app.test_db.completed == []


@pytest.mark.asyncio
async def test_webhook_marks_ptb_handler_error_failed(configured_app):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp(outcome="handler_error")

    response = await post_update(configured_app)

    assert response.status_code == 500
    assert configured_app.test_db.failed[0][2] == "handler_error"
    assert configured_app.test_db.completed == []


@pytest.mark.asyncio
async def test_webhook_times_out_and_releases_claim(configured_app, monkeypatch):
    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp(outcome="timeout")
    monkeypatch.setattr(main_module, "WEBHOOK_PROCESSING_TIMEOUT_SECONDS", 0.01)

    response = await post_update(configured_app)

    assert response.status_code == 500
    assert configured_app.test_db.failed[0][0] == 7001
    assert configured_app.test_db.completed == []



@pytest.mark.asyncio
async def test_webhook_rejects_oversized_chunked_body_without_content_length(configured_app):
    from fastapi import HTTPException
    from starlette.requests import Request

    configured_app.test_db = FakeDatabase()
    configured_app.test_telegram_app = FakeTelegramApp()

    # No Content-Length: simulate an oversized chunked request arriving in
    # separate ASGI messages. The route must reject it before JSON parsing.
    chunks = [
        b" " * 600_000,
        b" " * 450_000 + b'{"update_id":7001}',
    ]

    async def chunk_messages():
        for index, chunk in enumerate(chunks):
            yield {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }

    iterator = chunk_messages().__aiter__()

    async def receive():
        return await iterator.__anext__()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/telegram/webhook",
        "raw_path": b"/telegram/webhook",
        "query_string": b"",
        "headers": [
            (b"x-telegram-bot-api-secret-token", b"test-webhook-secret"),
            (b"transfer-encoding", b"chunked"),
        ],
        "server": ("test", 80),
        "client": ("127.0.0.1", 12345),
        "root_path": "",
        "app": configured_app,
    }
    request = Request(scope, receive)

    with pytest.raises(HTTPException) as exc_info:
        await main_module.telegram_webhook(request)

    assert exc_info.value.status_code == 413
    assert configured_app.test_db.claim_calls == []
    assert configured_app.test_telegram_app.processed == []
