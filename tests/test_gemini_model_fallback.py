import httpx
import pytest

from app.ai.providers import Provider


@pytest.mark.asyncio
async def test_gemini_tries_next_model_after_rate_limit(monkeypatch):
    attempted = []

    class FakeResponse:
        def __init__(self, model):
            self.model = model

        def raise_for_status(self):
            if self.model == "gemini-3.8-flash":
                request = httpx.Request("POST", "https://example.test")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("rate limited", request=request, response=response)

        def json(self):
            return {
                "model": self.model,
                "choices": [{
                    "message": {"content": "Fallback answer"},
                    "finish_reason": "stop",
                }],
            }

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            attempted.append(json["model"])
            return FakeResponse(json["model"])

    monkeypatch.setattr("app.ai.providers.httpx.AsyncClient", FakeClient)
    provider = Provider(
        "gemini",
        "test-key",
        "gemini-3.8-flash",
        "https://example.test",
        ("gemini-3.5-flash-lite", "gemini-3.7-flash"),
    )

    result = await provider.generate([{"role": "user", "content": "Hi"}], 2, 100)

    assert attempted == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    assert result["text"] == "Fallback answer"
    assert result["model"] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_gemini_does_not_switch_models_for_non_retryable_status(monkeypatch):
    attempted = []

    class FakeResponse:
        def raise_for_status(self):
            request = httpx.Request("POST", "https://example.test")
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError("bad request", request=request, response=response)

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            attempted.append(json["model"])
            return FakeResponse()

    monkeypatch.setattr("app.ai.providers.httpx.AsyncClient", FakeClient)
    provider = Provider(
        "gemini",
        "test-key",
        "gemini-3.8-flash",
        "https://example.test",
        ("gemini-3.5-flash-lite",),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate([{"role": "user", "content": "Hi"}], 2, 100)

    assert attempted == ["gemini-3.8-flash"]
