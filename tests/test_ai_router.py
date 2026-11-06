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


def test_provider_failure_diagnostics_classify_empty_response():
    details = AIRouter._failure_diagnostics(
        RuntimeError("gemini returned null content")
    )
    assert details["category"] == "empty_response"
    assert details["status"] is None
    assert details["response_bytes"] is None


def test_provider_failure_diagnostics_capture_safe_http_metadata():
    import httpx

    request = httpx.Request("POST", "https://provider.example/chat/completions")
    response = httpx.Response(
        503,
        request=request,
        headers={"x-request-id": "req-123"},
        content=b"private provider response",
    )
    error = httpx.HTTPStatusError(
        "provider unavailable",
        request=request,
        response=response,
    )

    details = AIRouter._failure_diagnostics(error)
    assert details == {
        "category": "http_status",
        "status": 503,
        "response_bytes": len(b"private provider response"),
        "request_id": "req-123",
    }


def test_provider_failure_diagnostics_classify_timeout():
    import httpx

    details = AIRouter._failure_diagnostics(
        httpx.ReadTimeout("request timed out")
    )
    assert details["category"] == "timeout"
