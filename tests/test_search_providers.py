from unittest.mock import AsyncMock

import pytest

from app.ai.research import AnimeResearchService


def test_decodo_organic_results_are_normalised():
    rows = AnimeResearchService._normalise_decodo_results({
        "organic": [
            {
                "title": "Official Anime Announcement",
                "link": "https://example.com/anime-news",
                "description": "An anime studio announced a new project.",
                "rank": 1,
            }
        ]
    })

    assert rows == [
        {
            "title": "Official Anime Announcement",
            "url": "https://example.com/anime-news",
            "content": "An anime studio announced a new project.",
            "published_date": "",
            "score": None,
        }
    ]


def test_langsearch_page_results_are_normalised():
    rows = AnimeResearchService._normalise_langsearch_results({
        "data": {
            "webPages": {
                "value": [
                    {
                        "name": "Anime Publisher News",
                        "url": "https://publisher.example/news",
                        "text": "A manga publisher confirmed an anime announcement.",
                        "datePublished": "2026-11-08",
                    }
                ]
            }
        }
    })

    assert rows[0]["title"] == "Anime Publisher News"
    assert rows[0]["url"] == "https://publisher.example/news"
    assert rows[0]["content"].startswith("A manga publisher")
    assert rows[0]["published_date"] == "2026-11-08"


@pytest.mark.asyncio
async def test_search_fallback_uses_configured_order_and_stops_on_verified_result():
    service = AnimeResearchService(
        search_provider_order=["decodo", "langsearch", "tavily"]
    )
    expected = {
        "answer": "Verified anime update",
        "citations": [{"title": "Source", "url": "https://example.com"}],
        "evidence": [],
        "verification": {},
        "provider": "decodo",
        "usage": {},
    }
    service.decodo_search_answer = AsyncMock(return_value=expected)
    service.langsearch_search_answer = AsyncMock(return_value=None)
    service.tavily_search_answer = AsyncMock(return_value=None)

    result = await service.search_fallback_answer("latest anime news", "english")

    assert result == expected
    service.decodo_search_answer.assert_awaited_once_with("latest anime news", "english")
    service.langsearch_search_answer.assert_not_awaited()
    service.tavily_search_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_fallback_continues_after_provider_failure():
    service = AnimeResearchService(
        search_provider_order=["decodo", "langsearch", "tavily"]
    )
    expected = {"provider": "langsearch", "citations": [{"url": "https://example.com"}]}
    service.decodo_search_answer = AsyncMock(return_value=None)
    service.langsearch_search_answer = AsyncMock(return_value=expected)
    service.tavily_search_answer = AsyncMock(return_value=None)

    result = await service.search_fallback_answer("latest anime news", "tenglish")

    assert result == expected
    service.decodo_search_answer.assert_awaited_once()
    service.langsearch_search_answer.assert_awaited_once()
    service.tavily_search_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_fallback_returns_none_when_all_providers_fail():
    service = AnimeResearchService(
        search_provider_order=["decodo", "langsearch", "tavily"]
    )
    service.decodo_search_answer = AsyncMock(return_value=None)
    service.langsearch_search_answer = AsyncMock(return_value=None)
    service.tavily_search_answer = AsyncMock(return_value=None)

    assert await service.search_fallback_answer("latest anime news") is None


def test_historical_queries_do_not_get_recent_only_filter():
    assert AnimeResearchService._is_historical_query("Naruto anime news from 2017")
    assert AnimeResearchService._is_historical_query("history of One Piece manga announcements")
    assert not AnimeResearchService._is_historical_query("latest anime news today")
