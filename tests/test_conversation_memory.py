import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.db import Database


class FakeConnection:
    def __init__(self):
        self.execute = AsyncMock()
        self.fetchval = AsyncMock(return_value=None)
        self.transaction_calls = 0

    @asynccontextmanager
    async def transaction(self):
        self.transaction_calls += 1
        yield


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    def __getattr__(self, name):
        return getattr(self.connection, name)


@pytest.mark.asyncio
async def test_save_exchange_persists_both_roles_in_one_transaction():
    db = Database(settings=None)
    pool = FakePool()
    db.pool = pool

    saved = await db.save_exchange(123, "Who is Luffy's father?", "Monkey D. Dragon.", 987)

    assert saved is True
    assert pool.connection.transaction_calls == 1
    assert pool.connection.execute.await_count == 2
    user_call = pool.connection.execute.await_args_list[0]
    assistant_call = pool.connection.execute.await_args_list[1]
    assert "'user'" in user_call.args[0]
    assert user_call.args[1:] == (123, "Who is Luffy's father?", 987)
    assert "'assistant'" in assistant_call.args[0]
    assert assistant_call.args[1:] == (123, "Monkey D. Dragon.", 987)


@pytest.mark.asyncio
async def test_save_exchange_is_idempotent_for_same_telegram_update():
    db = Database(settings=None)
    pool = FakePool()
    pool.connection.fetchval.return_value = 1
    db.pool = pool

    saved = await db.save_exchange(123, "duplicate", "duplicate answer", 987)

    assert saved is False
    assert pool.connection.execute.await_count == 0


@pytest.mark.asyncio
async def test_conversation_state_writes_only_explicit_entity_context():
    db = Database(settings=None)
    pool = FakePool()
    db.pool = pool
    entities = [{"type": "anime_title", "name": "One Piece", "source": "explicit_user_turn"}]

    await db.update_conversation_state(123, "One Piece", entities, 987)

    args = pool.connection.execute.await_args.args
    assert args[1] == 123
    assert args[2] == "One Piece"
    assert json.loads(args[3]) == entities
    assert args[4] == 987
