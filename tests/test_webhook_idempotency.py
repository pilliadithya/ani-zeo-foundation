import uuid

import pytest

from app.db import Database


class FakePool:
    def __init__(self, fetchrow_result=None):
        self.fetchrow_result = fetchrow_result
        self.fetchrow_calls = []
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"


class FakeSettings:
    database_url = "postgresql://unused"


@pytest.mark.asyncio
async def test_claim_update_returns_token_when_inserted():
    token = uuid.uuid4()
    pool = FakePool(fetchrow_result={"claim_token": token})
    db = Database(FakeSettings())
    db.pool = pool

    assert await db.claim_telegram_update(123) == str(token)
    query, args = pool.fetchrow_calls[0]
    assert "claim_token" in query
    assert "on conflict (update_id) do update" in query.lower()
    assert "returning claim_token" in query.lower()
    assert args[0] == 123
    assert isinstance(args[1], uuid.UUID)


@pytest.mark.asyncio
async def test_claim_update_returns_none_for_duplicate():
    pool = FakePool(fetchrow_result=None)
    db = Database(FakeSettings())
    db.pool = pool

    assert await db.claim_telegram_update(123) is None


@pytest.mark.asyncio
async def test_complete_update_is_fenced_by_claim_token():
    pool = FakePool()
    db = Database(FakeSettings())
    db.pool = pool
    token = str(uuid.uuid4())

    await db.complete_telegram_update(123, token)

    query, args = pool.execute_calls[0]
    assert "status='completed'" in query.lower()
    assert "claim_token=$2" in query.lower()
    assert args == (123, token)


@pytest.mark.asyncio
async def test_fail_update_is_fenced_by_claim_token():
    pool = FakePool()
    db = Database(FakeSettings())
    db.pool = pool
    token = str(uuid.uuid4())

    await db.fail_telegram_update(123, token, "handler_error")

    query, args = pool.execute_calls[0]
    assert "status='failed'" in query.lower()
    assert "claim_token=$2" in query
    assert args == (123, token, "handler_error")
