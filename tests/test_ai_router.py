import pytest
from app.ai.router import AIRouter
class FakeProvider:
    def __init__(self,name,key,response=None,error=None): self.name,self.api_key,self.response,self.error=name,key,response,error
    async def generate(self,messages,timeout,max_tokens):
        if self.error: raise self.error
        return self.response
class FakeSettings:
    provider_order=["gemini","groq"]; ai_timeout_seconds=1; ai_max_output_tokens=100
    gemini_api_key="a"; gemini_model="m1"; groq_api_key="b"; groq_model="m2"
    nvidia_api_key=""; nvidia_model="m3"; openrouter_api_key=""; openrouter_model="m4"
@pytest.mark.asyncio
async def test_fallback_provider_used():
    r=AIRouter(FakeSettings()); r.providers["gemini"]=FakeProvider("gemini","a",error=RuntimeError("offline")); r.providers["groq"]=FakeProvider("groq","b",response="Hello")
    answer,name=await r.reply([{"role":"user","content":"hi"}],"english")
    assert (answer,name)==("Hello","groq")
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
    assert "untrusted reference only" in system


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
                "results": [{"title": "Official announcement", "url": "https://example.com/news", "content": "Official studio update."}],
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
            assert kwargs["json"]["tools"] == [{"google_search_retrieval": {}}]
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
                    "content": "The studio confirmed a future release.",
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
    assert "Official anime release update" in result["answer"]
    assert "2026-11-07" in result["answer"]
    assert "unverified summary" not in result["answer"]
    assert "not a verified release calendar" in result["answer"]


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
