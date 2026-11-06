import pytest
import uuid

from app.db import Database


class FakePool:
    def __init__(self, claim_result=None):
        self.claim_result = claim_result
        self.fetch_calls = []
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        self.fetch_calls.append((query, *args))
        return self.claim_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


@pytest.mark.asyncio
async def test_claim_telegram_update_returns_true_for_new_update():
    db = Database(settings=None)
    token = uuid.uuid4()
    db.pool = FakePool({"claim_token": token})

    claimed = await db.claim_telegram_update(123)

    assert claimed == str(token)
    query, update_id, token_arg = db.pool.fetch_calls[0]
    assert update_id == 123
    assert isinstance(token_arg, uuid.UUID)
    assert token_arg != token  # Database creates its own unique ownership token.
    assert "on conflict (update_id) do update" in query.lower()
    assert "status <> 'completed'" in query.lower()
    assert "interval '10 minutes'" in query.lower()


@pytest.mark.asyncio
async def test_claim_telegram_update_returns_false_for_duplicate():
    db = Database(settings=None)
    db.pool = FakePool(None)

    claimed = await db.claim_telegram_update(123)

    assert claimed is None


@pytest.mark.asyncio
async def test_complete_telegram_update_marks_claim_completed():
    db = Database(settings=None)
    db.pool = FakePool()

    await db.complete_telegram_update(456, str(uuid.uuid4()))

    query, args = db.pool.execute_calls[0]
    assert "set status='completed'" in query.lower()
    assert args[0] == 456 and isinstance(args[1], uuid.UUID)


@pytest.mark.asyncio
async def test_release_telegram_update_removes_failed_claim():
    db = Database(settings=None)
    db.pool = FakePool()

    await db.release_telegram_update(789, str(uuid.uuid4()))

    query, args = db.pool.execute_calls[0]
    assert "delete from public.processed_telegram_updates" in query.lower()
    assert args[0] == 789 and isinstance(args[1], uuid.UUID)


# Exercise the real FastAPI webhook endpoint with concurrent ASGI requests.
# The database is an in-memory atomic fake; PostgreSQL concurrency still
# requires a separate test database to validate end-to-end.
import asyncio
from types import SimpleNamespace
import os

import httpx
from fastapi import FastAPI

# app.main creates Settings at import time; provide non-secret test-only
# values so endpoint tests do not require production credentials.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

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
            token = str(uuid.uuid4())
            self.claimed.add(update_id)
            self.tokens = getattr(self, 'tokens', {})
            self.tokens[update_id] = token
            return token

    async def complete_telegram_update(self, update_id, claim_token):
        async with self.lock:
            if self.tokens.get(update_id) == claim_token:
                self.claimed.discard(update_id)
                self.completed.add(update_id)

    async def release_telegram_update(self, update_id, claim_token):
        async with self.lock:
            if self.tokens.get(update_id) == claim_token:
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

    def fake_de_json(payload, bot):
        return SimpleNamespace(
            effective_message=SimpleNamespace(message_id=payload["update_id"])
        )

    monkeypatch.setattr(main_module.Update, "de_json", staticmethod(fake_de_json))
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


@pytest.mark.asyncio
async def test_postgres_atomically_claims_concurrent_duplicate_updates():
    """Exercise the production INSERT..ON CONFLICT claim against real PostgreSQL."""
    import os
    import time

    import asyncpg

    dsn = os.getenv("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is only configured in the CI PostgreSQL job")

    connection = await asyncpg.connect(dsn)
    update_id = time.time_ns()

    try:
        await connection.execute(
            """
            create table if not exists public.processed_telegram_updates (
                update_id bigint primary key,
                status text not null check (status in ('processing', 'completed')),
                claim_token uuid not null,
                claimed_at timestamptz not null default now(),
                completed_at timestamptz
            )
            """
        )

        claim_sql = """
            insert into public.processed_telegram_updates (update_id, status, claim_token)
            values ($1, 'processing', $2)
            on conflict (update_id) do update
              set status='processing', claim_token=$2, claimed_at=now(), completed_at=null
              where processed_telegram_updates.status <> 'completed'
                and processed_telegram_updates.claimed_at < now() - interval '10 minutes'
            returning update_id
        """

        async def claim():
            return await connection.fetchrow(claim_sql, update_id, uuid.uuid4())

        # Separate PostgreSQL connections are required to test real concurrent
        # transactions, rather than serializing through one connection.
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=2)
        try:
            async def pool_claim():
                async with pool.acquire() as conn:
                    return await conn.fetchrow(claim_sql, update_id, uuid.uuid4())

            results = await asyncio.gather(pool_claim(), pool_claim())
            assert sum(result is not None for result in results) == 1

            await pool.execute(
                """
                update public.processed_telegram_updates
                set status='completed', completed_at=now()
                where update_id=$1
                """,
                update_id,
            )
            duplicate = await pool_claim()
            assert duplicate is None
        finally:
            await pool.close()
    finally:
        await connection.execute(
            "delete from public.processed_telegram_updates where update_id=$1",
            update_id,
        )
        await connection.close()
