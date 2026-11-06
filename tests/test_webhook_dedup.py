import pytest

from app.db import Database


class FakePool:
    def __init__(self, claim_result=None):
        self.claim_result = claim_result
        self.fetch_calls = []
        self.execute_calls = []

    async def fetchrow(self, query, update_id):
        self.fetch_calls.append((query, update_id))
        return self.claim_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_claim_telegram_update_returns_true_for_new_update():
    db = Database(settings=None)
    db.pool = FakePool({"update_id": 123})

    claimed = await db.claim_telegram_update(123)

    assert claimed is True
    query, update_id = db.pool.fetch_calls[0]
    assert update_id == 123
    assert "on conflict (update_id) do update" in query.lower()
    assert "status <> 'completed'" in query.lower()
    assert "interval '10 minutes'" in query.lower()


@pytest.mark.asyncio
async def test_claim_telegram_update_returns_false_for_duplicate():
    db = Database(settings=None)
    db.pool = FakePool(None)

    claimed = await db.claim_telegram_update(123)

    assert claimed is False


@pytest.mark.asyncio
async def test_complete_telegram_update_marks_claim_completed():
    db = Database(settings=None)
    db.pool = FakePool()

    await db.complete_telegram_update(456)

    query, args = db.pool.execute_calls[0]
    assert "set status='completed'" in query.lower()
    assert args == (456,)


@pytest.mark.asyncio
async def test_release_telegram_update_removes_failed_claim():
    db = Database(settings=None)
    db.pool = FakePool()

    await db.release_telegram_update(789)

    query, args = db.pool.execute_calls[0]
    assert "delete from public.processed_telegram_updates" in query.lower()
    assert args == (789,)


# Exercise the real FastAPI webhook endpoint with concurrent ASGI requests.
# The database is an in-memory atomic fake; PostgreSQL concurrency still
# requires a separate test database to validate end-to-end.
import asyncio
import json
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from app import main as main_module


class AtomicFakeDatabase:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.claimed = set()
        self.completed = set()

    async def claim_telegram_update(self, update_id):
        async with self.lock:
            if update_id in self.claimed or update_id in self.completed:
                return False
            self.claimed.add(update_id)
            return True

    async def complete_telegram_update(self, update_id):
        async with self.lock:
            self.claimed.discard(update_id)
            self.completed.add(update_id)

    async def release_telegram_update(self, update_id):
        async with self.lock:
            self.claimed.discard(update_id)


class CountingTelegramApp:
    def __init__(self, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first
        self.bot = object()

    async def process_update(self, update):
        self.calls += 1
        await asyncio.sleep(0.02)
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated handler failure")


def make_webhook_client(monkeypatch, db, telegram_app):
    monkeypatch.setattr(main_module.settings, "webhook_secret", "test-secret")
    api = FastAPI()
    api.state.db = db
    api.state.telegram_app = telegram_app
    api.add_api_route(
        "/telegram/webhook",
        main_module.telegram_webhook,
        methods=["POST"],
    )

    async def fake_de_json(payload, bot):
        return SimpleNamespace(
            effective_message=SimpleNamespace(message_id=payload["update_id"])
        )

    monkeypatch.setattr(main_module.Update, "de_json", fake_de_json)
    transport = httpx.ASGITransport(app=api)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_concurrent_duplicate_webhooks_process_update_once(monkeypatch):
    db = AtomicFakeDatabase()
    telegram_app = CountingTelegramApp()
    async with make_webhook_client(monkeypatch, db, telegram_app) as client:
        payload = {"update_id": 9001, "message": {"message_id": 77}}
        headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}

        responses = await asyncio.gather(
            client.post("/telegram/webhook", json=payload, headers=headers),
            client.post("/telegram/webhook", json=payload, headers=headers),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert telegram_app.calls == 1
    assert 9001 in db.completed


@pytest.mark.asyncio
async def test_failed_webhook_releases_claim_for_retry(monkeypatch):
    db = AtomicFakeDatabase()
    telegram_app = CountingTelegramApp(fail_first=True)
    async with make_webhook_client(monkeypatch, db, telegram_app) as client:
        payload = {"update_id": 9002, "message": {"message_id": 78}}
        headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}

        first = await client.post("/telegram/webhook", json=payload, headers=headers)
        second = await client.post("/telegram/webhook", json=payload, headers=headers)

    assert first.status_code == 500
    assert second.status_code == 200
    assert telegram_app.calls == 2
    assert 9002 in db.completed
