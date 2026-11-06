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
async def test_claim_update_returns_true_when_inserted():
    pool = FakePool(fetchrow_result={"update_id": 123})
    db = Database(FakeSettings())
    db.pool = pool

    assert await db.claim_telegram_update(123) is True
    query, args = pool.fetchrow_calls[0]
    assert "ON CONFLICT (update_id) DO UPDATE" in query
    assert "RETURNING update_id" in query
    assert args == (123,)


@pytest.mark.asyncio
async def test_claim_update_returns_false_for_duplicate():
    pool = FakePool(fetchrow_result=None)
    db = Database(FakeSettings())
    db.pool = pool

    assert await db.claim_telegram_update(123) is False


@pytest.mark.asyncio
async def test_complete_update_marks_update_completed():
    pool = FakePool()
    db = Database(FakeSettings())
    db.pool = pool

    await db.complete_telegram_update(123)

    query, args = pool.execute_calls[0]
    assert "status='completed'" in query
    assert args == (123,)


@pytest.mark.asyncio
async def test_fail_update_records_safe_error_label():
    pool = FakePool()
    db = Database(FakeSettings())
    db.pool = pool

    await db.fail_telegram_update(123, "handler_error")

    query, args = pool.execute_calls[0]
    assert "status='failed'" in query
    assert args == (123, "handler_error")
