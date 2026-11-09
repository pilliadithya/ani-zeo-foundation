from types import SimpleNamespace

import pytest

from app.db import Database


class FakePool:
    def __init__(self, rows=None):
        self.executed = []
        self.fetched = []
        self.rows = rows or []

    async def execute(self, *args):
        self.executed.append(args)

    async def fetch(self, *args):
        self.fetched.append(args)
        return self.rows


@pytest.mark.asyncio
async def test_archive_stores_only_secure_verified_source_excerpts():
    database = Database(SimpleNamespace(database_url="postgresql://unused"))
    pool = FakePool()
    database.pool = pool

    stored = await database.store_research_evidence([
        {
            "title": "Official anime announcement",
            "url": "https://studio.example/news",
            "domain": "studio.example",
            "snippet": "A studio announced an anime project.",
            "published": "2026-11-08",
            "verification_status": "primary_source",
        },
        {
            "title": "Unsafe result",
            "url": "http://unsafe.example/news",
            "snippet": "Not stored",
            "verification_status": "primary_source",
        },
        {
            "title": "Unknown provenance",
            "url": "https://unknown.example/news",
            "snippet": "Not stored",
            "verification_status": "maybe_true",
        },
    ], "decodo")

    assert stored == 1
    assert len(pool.executed) == 1
    assert pool.executed[0][1] == "https://studio.example/news"
    assert "anime_research_evidence" in pool.executed[0][0]


@pytest.mark.asyncio
async def test_archive_retrieval_uses_parameterised_full_text_search_and_bounded_limit():
    database = Database(SimpleNamespace(database_url="postgresql://unused"))
    expected = [{
        "title": "One Piece historical update",
        "url": "https://publisher.example/one-piece",
        "snippet": "One Piece manga update from 2017.",
    }]
    pool = FakePool(rows=expected)
    database.pool = pool

    result = await database.search_research_evidence("  One Piece 2017  ", limit=99)

    assert result == expected
    query, search_text, limit = pool.fetched[0]
    assert "websearch_to_tsquery" in query
    assert search_text == "One Piece 2017"
    assert limit == 8


@pytest.mark.asyncio
async def test_archive_retrieval_returns_empty_for_blank_query():
    database = Database(SimpleNamespace(database_url="postgresql://unused"))
    pool = FakePool()
    database.pool = pool

    assert await database.search_research_evidence("   ") == []
    assert pool.fetched == []
