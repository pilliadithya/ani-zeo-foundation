from app.db import Database


class FakePool:
    def __init__(self, claim_result):
        self.claim_result = claim_result
        self.executed = []

    async def fetchrow(self, query, update_id):
        self.query = query
        self.update_id = update_id
        return self.claim_result

    async def execute(self, query):
        self.executed.append(query)


def test_claim_telegram_update_returns_true_when_claim_inserted():
    db = Database(settings=None)
    db.pool = FakePool({"update_id": 123})

    import asyncio
    claimed = asyncio.run(db.claim_telegram_update(123))

    assert claimed is True
    assert db.pool.update_id == 123


def test_claim_telegram_update_returns_false_for_duplicate():
    db = Database(settings=None)
    db.pool = FakePool(None)

    import asyncio
    claimed = asyncio.run(db.claim_telegram_update(123))

    assert claimed is False
