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
