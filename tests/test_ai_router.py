import pytest
from app.ai.router import AIRouter
class FakeProvider:
    def __init__(self,name,key,response=None,error=None): self.name,self.api_key,self.response,self.error=name,key,response,error
    async def generate(self,messages,timeout,max_tokens):
        self.last_max_tokens = max_tokens
        if self.error: raise self.error
        return self.response
class FakeSettings:
    provider_order=["gemini","groq"]; ai_timeout_seconds=1; ai_max_output_tokens=100
    gemini_api_key="a"; gemini_model="m1"; groq_api_key="b"; groq_model="m2"
    nvidia_api_key=""; nvidia_model="m3"; openrouter_api_key=""; openrouter_model="m4"
@pytest.mark.asyncio
async def test_fallback_provider_used():
    r=AIRouter(FakeSettings()); r.providers["gemini"]=FakeProvider("gemini","a",error=RuntimeError("offline")); r.providers["groq"]=FakeProvider("groq","b",response="Hello")
    answer,name,usage=await r.reply([{"role":"user","content":"hi"}],"english")
    assert (answer,name)==("Hello","groq")
    assert usage.get('input_tokens') is None
    assert usage.get('output_tokens') is None
    assert usage.get('estimated_input_tokens', 0) > 0
@pytest.mark.asyncio
async def test_missing_keys_fails_cleanly():
    s=FakeSettings(); s.provider_order=["nvidia","openrouter"]
    with pytest.raises(RuntimeError,match="No AI provider"): await AIRouter(s).reply([{"role":"user","content":"hi"}])


from app.ai.research import AnimeResearchService


def test_scope_gate_allows_anime_and_greetings():
    assert AnimeResearchService.scope_decision("Tell me about Naruto anime") == "anime"
    assert AnimeResearchService.scope_decision("hello bro") == "greeting"


def test_scope_gate_rejects_off_topic_without_ai():
    assert AnimeResearchService.scope_decision("Help me write Python code") == "redirect"
    assert AnimeResearchService.scope_decision("Explain photosynthesis") == "redirect"


def test_scope_gate_allows_anime_follow_up():
    history = [{"role": "user", "content": "Tell me about One Piece anime"}]
    assert AnimeResearchService.scope_decision("Who is his brother?", history) == "anime"


def test_live_search_only_for_fresh_information():
    assert AnimeResearchService.needs_live_search("Latest One Piece news")
    assert AnimeResearchService.needs_live_search("Where can I watch anime today?")
    assert not AnimeResearchService.needs_live_search("Explain Naruto's character development")


def test_title_extraction_and_metadata_context():
    assert AnimeResearchService.extract_title("Tell me about Frieren") == "Frieren"
    context = AnimeResearchService.context_for({"title": "Frieren", "source": "AniList", "genres": ["Adventure"]})
    assert "Title: Frieren" in context
    assert "Source: AniList" in context


def test_google_search_disabled_without_gemini_key():
    import asyncio
    service = AnimeResearchService()
    assert asyncio.run(service.google_grounded_answer("Latest anime news")) is None


def test_metadata_cache_expires_and_returns_copy():
    service = AnimeResearchService()
    service._store("naruto", {"title": "Naruto"})
    cached = service._cached("naruto")
    cached["title"] = "changed"
    assert service._cached("naruto")["title"] == "Naruto"


def test_named_anime_lookup_is_allowed_but_generic_explanation_is_not():
    assert AnimeResearchService.scope_decision("Tell me about Frieren") == "anime"
    assert AnimeResearchService.scope_decision("Explain photosynthesis") == "redirect"


def test_router_includes_retrieved_data_as_untrusted_context():
    router = AIRouter(FakeSettings())
    messages = router._build_messages(
        [{"role": "user", "content": "Tell me about Frieren"}],
        "english",
        research_context="Title: Frieren\\nSource: AniList",
    )
    system = messages[0]["content"]
    assert "Title: Frieren" in system
    assert "RESEARCH RESPONSE MODE" in system


@pytest.mark.asyncio
async def test_live_search_requires_grounding_sources(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Unverified current claim"}]}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(api_key="test-key")
    assert await service.google_grounded_answer("Latest anime release announcements") is None


@pytest.mark.asyncio
async def test_live_search_failure_does_not_cache_unverified_answer(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "Stale answer"}]}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(api_key="test-key")
    assert await service.google_grounded_answer("Latest anime news") is None
    assert not any(key.startswith("live:") for key in service.cache)


@pytest.mark.asyncio
async def test_tavily_backup_returns_cited_search_results(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "answer": "A new anime announcement was published.",
                "results": [{"title": "Official anime announcement", "url": "https://example.com/news", "content": "Official anime studio update."}],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(tavily_api_key="test-key")
    result = await service.tavily_search_answer("Latest anime announcements")
    assert result["provider"] == "tavily"
    assert result["citations"][0]["url"] == "https://example.com/news"
    assert result["evidence"][0]["verification_status"] == "unverified_publisher"
    assert result["verification"]["overall_status"] == "unverified_sources_only"


@pytest.mark.asyncio
async def test_tavily_backup_rejects_results_without_https_sources(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"answer": "Uncited answer", "results": [{"title": "Bad source", "url": "http://example.com", "content": "No secure source."}]}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(tavily_api_key="test-key")
    assert await service.tavily_search_answer("Latest anime news") is None


def test_grounding_default_uses_supported_current_flash_model():
    service = AnimeResearchService(api_key="test-key")
    assert service.model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_google_grounding_extracts_citations(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates": [{
                "content": {"parts": [{"text": "Upcoming anime release: Example title."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"title": "Official source", "uri": "https://example.com/anime"}}
                    ],
                    "groundingSupports": [{
                        "segment": {"startIndex": 0, "endIndex": 43, "text": "Upcoming anime release: Example title."},
                        "groundingChunkIndices": [0],
                    }],
                },
            }]}

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            assert kwargs["json"]["tools"] == [{"google_search": {}}]
            assert kwargs["json"]["generationConfig"]["temperature"] == 0.2
            return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(api_key="test-key")
    result = await service.google_grounded_answer("Latest anime news")
    assert result["citations"][0]["url"] == "https://example.com/anime"
    assert result["answer"].startswith("Upcoming anime")


@pytest.mark.asyncio
async def test_tavily_uses_source_snippets_not_unverified_answer(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "answer": "This unverified summary must not be displayed.",
                "results": [{
                    "title": "Official anime release update",
                    "url": "https://example.com/release",
                    "content": "The anime studio confirmed a future anime release.",
                    "published_date": "2026-11-07",
                }],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            assert kwargs["json"]["include_answer"] is False
            return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(tavily_api_key="test-key")
    result = await service.tavily_search_answer("Upcoming anime releases")
    assert result["answer"].startswith("Hey! Here's the update I found.")
    assert "The anime studio confirmed a future anime release." in result["answer"]
    assert "unverified summary" not in result["answer"]
    assert "I won't fill in details they haven't confirmed" in result["answer"]


def test_grounding_coverage_rejects_unsupported_claims():
    answer = "One Piece has a new movie announced for December 2026. Naruto season 10 starts next month."
    supports = [{
        "segment": {"startIndex": 0, "endIndex": 59},
        "groundingChunkIndices": [0],
    }]
    assert not AnimeResearchService._grounding_covers_answer(answer, supports)


def test_grounding_coverage_accepts_supported_sentences():
    answer = "The studio confirmed a new anime film for December 2026."
    supports = [{
        "segment": {"startIndex": 0, "endIndex": len(answer)},
        "groundingChunkIndices": [0],
    }]
    assert AnimeResearchService._grounding_covers_answer(answer, supports)


def test_grounding_coverage_rejects_missing_supports():
    assert not AnimeResearchService._grounding_covers_answer("A long factual sentence with a claim.", [])


@pytest.mark.asyncio
async def test_tavily_backup_rejects_unrelated_crypto_results(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "results": [{
                    "title": "Global cryptocurrency investment platform",
                    "url": "https://example.com/crypto",
                    "content": "Bitcoin, Ethereum and Web3 investment information.",
                }],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            assert any(name in kwargs["json"]["query"] for name in ("One Piece", "Naruto Boruto", "Bleach"))
            return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(tavily_api_key="test-key")
    result = await service.tavily_search_answer(
        "Give me the latest confirmed Big 3 anime updates as of today."
    )
    assert result is None


def test_tavily_relevance_guard_requires_big_three_franchise_match():
    relevant = {
        "title": "One Piece anime official update",
        "content": "The latest One Piece anime announcement.",
        "url": "https://example.com/one-piece",
    }
    irrelevant = {
        "title": "Cryptocurrency investment platform",
        "content": "Bitcoin and Ethereum Web3 services.",
        "url": "https://example.com/crypto",
    }
    query = "Latest Big 3 anime updates"
    assert AnimeResearchService._is_relevant_anime_result(relevant, query)
    assert not AnimeResearchService._is_relevant_anime_result(irrelevant, query)


def test_big_three_filter_uses_headline_not_incidental_snippet_mentions():
    relevant = {
        "title": "One Piece anime announces new episode",
        "content": "A verified One Piece update.",
        "url": "https://example.com/one-piece-news",
    }
    irrelevant = {
        "title": "DayOne | Gaming roundup",
        "content": "A long roundup mentions One Piece once among many unrelated games.",
        "url": "https://example.com/dayone",
    }
    assert AnimeResearchService._is_relevant_anime_result(
        relevant, "Latest Big Three anime updates"
    )
    assert not AnimeResearchService._is_relevant_anime_result(
        irrelevant, "Latest Big Three anime updates"
    )


def test_search_title_and_snippet_are_cleaned_for_telegram():
    item = {
        "title": " | DayOne",
        "url": "https://www.example.com/news",
    }
    assert AnimeResearchService._clean_search_title(item) == "example.com"
    assert AnimeResearchService._clean_search_snippet(
        "5 days ago - " + ("Nintendo gaming roundup " * 30), limit=100
    ).endswith("…")


@pytest.mark.asyncio
async def test_tavily_big_three_results_are_grouped_and_compact(monkeypatch):
    import app.ai.research as research_module

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "results": [
                    {
                        "title": "One Piece anime official update",
                        "url": "https://anime.example.com/one-piece",
                        "content": "The official One Piece anime update includes a new broadcast announcement. " * 5,
                        "published_date": "2026-11-07",
                    },
                    {
                        "title": "DayOne gaming roundup",
                        "url": "https://games.example.com/dayone",
                        "content": "A gaming roundup with an incidental One Piece mention.",
                        "published_date": "2026-11-07",
                    },
                    {
                        "title": "Bleach anime news",
                        "url": "https://anime.example.com/bleach",
                        "content": "The Bleach anime news item reports a franchise update.",
                        "published_date": "2026-11-06",
                    },
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(research_module.httpx, "AsyncClient", FakeClient)
    service = AnimeResearchService(tavily_api_key="test-key")
    result = await service.tavily_search_answer(
        "Give me latest Big Three anime updates"
    )
    assert result is not None
    assert "**One Piece:**" in result["answer"]
    assert "**Bleach:**" in result["answer"]
    assert "DayOne" not in result["answer"]
    assert "ANIME NEWS" not in result["answer"]
    assert "Checked 2026" not in result["answer"]
    assert len(result["answer"]) < 1800


def test_intent_detector_classifies_live_news_and_typos():
    detected = AnimeResearchService.detect_intent(
        "Give me latest anmie updatse for narutoo"
    )
    assert detected["intent"] == "live_news"
    assert detected["scope"] == "anime"
    assert detected["was_corrected"] is True
    assert "anime" in detected["normalized_text"].lower()
    assert "updates" in detected["normalized_text"].lower()
    assert "Naruto" in detected["normalized_text"]


def test_intent_detector_handles_greeting_with_bot_name():
    detected = AnimeResearchService.detect_intent("Hi Ani Zeo")
    assert detected["intent"] == "greeting"
    assert detected["scope"] == "greeting"


def test_intent_detector_understands_anime_follow_up_from_context():
    history = [{"role": "user", "content": "Tell me about One Piece anime"}]
    detected = AnimeResearchService.detect_intent("What about his brother?", history)
    assert detected["intent"] == "follow_up"
    assert detected["scope"] == "anime"


def test_intent_detector_keeps_unknown_names_unchanged():
    original = "Tell me about Xyzzq Anime"
    assert AnimeResearchService.correct_typos(original) == original


def test_intent_detector_recognizes_updates_without_news_keyword():
    detected = AnimeResearchService.detect_intent("One Piece updates")
    assert detected["intent"] == "live_news"


def test_intent_detector_does_not_treat_unrelated_current_question_as_anime_followup():
    history = [{"role": "user", "content": "Tell me about One Piece anime"}]
    detected = AnimeResearchService.detect_intent("What's the weather today?", history)
    assert detected["scope"] == "redirect"
    assert detected["intent"] == "unclear"


def test_output_budget_scales_with_requested_depth():
    assert AIRouter._output_budget([{"role": "user", "content": "Hi bro"}]) == 180
    assert AIRouter._output_budget([{"role": "user", "content": "Explain Gear 5"}]) == 420
    assert AIRouter._output_budget([{"role": "user", "content": "Explain Gear 5 in detail"}]) == 900


def test_token_estimate_is_nonzero_and_monotonic():
    short = AIRouter.estimate_tokens("Naruto")
    long = AIRouter.estimate_tokens("Naruto " * 100)
    assert short >= 1
    assert long > short


@pytest.mark.asyncio
async def test_reply_respects_configured_output_token_cap():
    settings = FakeSettings()
    settings.ai_max_output_tokens = 200
    router = AIRouter(settings)
    provider = FakeProvider("gemini", "a", response="Short answer")
    router.providers["gemini"] = provider
    answer, name, usage = await router.reply(
        [{"role": "user", "content": "Explain the entire One Piece story in detail"}],
        "english",
    )
    assert answer == "Short answer"
    assert name == "gemini"
    assert provider.last_max_tokens == 200
    assert usage.get('input_tokens') is None
    assert usage.get('output_tokens') is None
    assert usage.get('estimated_input_tokens', 0) > 0


def test_cost_estimate_requires_explicit_rates_and_actual_usage():
    settings = FakeSettings()
    settings.ai_cost_rates_json = '{"gemini":{"input_per_million_usd":0.1,"output_per_million_usd":0.4}}'
    router = AIRouter(settings)
    cost = router._estimate_cost_usd("gemini", {"input_tokens": 1000, "output_tokens": 500})
    assert cost == 0.0003
    assert router._estimate_cost_usd("gemini", {"input_tokens": None, "output_tokens": 500}) is None
    assert router._estimate_cost_usd("groq", {"input_tokens": 1000, "output_tokens": 500}) is None


def test_research_context_uses_evidence_only_writer_instructions():
    router = AIRouter(FakeSettings())
    messages = router._build_messages(
        [{"role": "user", "content": "Latest One Piece manga update?"}],
        "tenglish",
        research_context=(
            "CURRENT ANIME RESEARCH EVIDENCE\\n"
            "Overall evidence status: reported_by_reputable_sources\\n"
            "Excerpt: A publisher reported a new announcement."
        ),
    )
    system = messages[0]["content"]
    assert "RESEARCH RESPONSE MODE" in system
    assert "Never turn a search excerpt" in system
    assert "CURRENT ANIME RESEARCH EVIDENCE" in system


def test_compact_system_prompt_reduces_planned_input_tokens():
    router = AIRouter(FakeSettings())
    messages = router._build_messages(
        [{"role": "user", "content": "Hi"}],
        "english",
    )
    assert router.estimate_messages_tokens(messages) < 1_300
