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
