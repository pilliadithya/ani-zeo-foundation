import httpx
import pytest

from app.ai.providers import Provider


def test_normalize_openai_compatible_usage():
    result = Provider.normalize_usage({
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 35,
            "total_tokens": 155,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 5},
            "tool_use_prompt_tokens": 9,
        }
    })
    assert result["input_tokens"] == 120
    assert result["output_tokens"] == 35
    assert result["total_tokens"] == 155
    assert result["cached_input_tokens"] == 40
    assert result["thinking_tokens"] == 5
    assert result["tool_tokens"] == 9


def test_normalize_usage_does_not_invent_missing_token_counts():
    result = Provider.normalize_usage({})
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["total_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["thinking_tokens"] is None
    assert result["tool_tokens"] is None


def test_normalize_usage_derives_total_only_when_both_counts_exist():
    result = Provider.normalize_usage({
        "usage": {"input_tokens": 20, "output_tokens": 7}
    })
    assert result["total_tokens"] == 27
    assert result["cached_input_tokens"] is None


@pytest.mark.asyncio
async def test_gemini_uses_second_account_after_primary_account_rate_limit(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://example.test/chat/completions")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("rate limited", request=request, response=response)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, json):
            calls.append(headers["Authorization"])
            if len(calls) == 1:
                return FakeResponse(429, {})
            return FakeResponse(200, {
                "model": "gemini-test",
                "choices": [{"message": {"content": "Gemini secondary account answer"}, "finish_reason": "stop"}],
            })

    monkeypatch.setattr("app.ai.providers.httpx.AsyncClient", FakeClient)
    provider = Provider(
        name="gemini",
        api_key="primary-secret",
        model="gemini-test",
        base_url="https://example.test",
        fallback_api_keys=("secondary-secret",),
    )

    result = await provider.generate(
        [{"role": "user", "content": "anime question"}],
        timeout=2,
        max_tokens=100,
    )

    assert result["text"] == "Gemini secondary account answer"
    assert calls == ["Bearer primary-secret", "Bearer secondary-secret"]
