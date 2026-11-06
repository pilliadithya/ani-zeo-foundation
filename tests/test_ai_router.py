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


@pytest.mark.asyncio
async def test_nvidia_timeout_skips_second_attempt_and_falls_back():
    import httpx

    settings = FakeSettings()
    settings.provider_order = ["nvidia", "groq"]
    settings.nvidia_api_key = "nvidia-key"

    class TimeoutProvider(FakeProvider):
        def __init__(self):
            super().__init__("nvidia", "nvidia-key")
            self.calls = 0

        async def generate(self, messages, timeout, max_tokens):
            self.calls += 1
            raise httpx.ReadTimeout("simulated timeout")

    router = AIRouter(settings)
    nvidia = TimeoutProvider()
    router.providers["nvidia"] = nvidia
    router.providers["groq"] = FakeProvider("groq", "b", response="Fallback reply")

    answer, provider = await router.reply(
        [{"role": "user", "content": "hello"}],
        "english",
    )

    assert answer == "Fallback reply"
    assert provider == "groq"
    assert nvidia.calls == 1


@pytest.mark.asyncio
async def test_gemini_and_groq_fail_then_nvidia_succeeds():
    settings = FakeSettings()
    settings.provider_order = ["gemini", "groq", "nvidia"]
    settings.nvidia_api_key = "nvidia-key"

    router = AIRouter(settings)
    router.providers["gemini"] = FakeProvider(
        "gemini", "a", error=RuntimeError("Gemini unavailable")
    )
    router.providers["groq"] = FakeProvider(
        "groq", "b", error=RuntimeError("Groq unavailable")
    )
    router.providers["nvidia"] = FakeProvider(
        "nvidia", "nvidia-key", response="NVIDIA fallback reply"
    )

    answer, provider = await router.reply(
        [{"role": "user", "content": "hello"}],
        "english",
    )

    assert answer == "NVIDIA fallback reply"
    assert provider == "nvidia"


@pytest.mark.asyncio
async def test_gemini_failure_falls_back_to_groq_before_nvidia():
    settings = FakeSettings()
    settings.provider_order = ["gemini", "groq", "nvidia"]
    settings.nvidia_api_key = "nvidia-key"

    router = AIRouter(settings)
    router.providers["gemini"] = FakeProvider(
        "gemini", "a", error=RuntimeError("Gemini unavailable")
    )
    router.providers["groq"] = FakeProvider(
        "groq", "b", response="Groq fallback reply"
    )
    router.providers["nvidia"] = FakeProvider(
        "nvidia", "nvidia-key", response="Should not be used"
    )

    answer, provider = await router.reply(
        [{"role": "user", "content": "hello"}],
        "english",
    )

    assert answer == "Groq fallback reply"
    assert provider == "groq"
