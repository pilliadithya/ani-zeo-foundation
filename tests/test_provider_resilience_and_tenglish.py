import pytest

from app.ai.router import AIRouter


class Settings:
    provider_order = ["nvidia", "groq", "gemini", "openrouter"]
    ai_timeout_seconds = 12
    ai_total_timeout_seconds = 28
    ai_max_output_tokens = 1400
    ai_groq_retry_max_output_tokens = 1800
    ai_cost_rates_json = "{}"
    nvidia_api_key = "n"
    nvidia_model = "nvidia-model"
    groq_api_key = "g"
    groq_model = "openai/gpt-oss-120b"
    gemini_api_key = "m"
    gemini_model = "gemini-3.5-flash"
    gemini_fallback_model_list = []
    openrouter_api_key = "o"
    openrouter_model = "openrouter-model"


class TruncatedThenCompleteGroq:
    name = "groq"
    api_key = "g"
    model = "openai/gpt-oss-120b"

    def __init__(self):
        self.budgets = []

    async def generate(self, messages, timeout, max_tokens):
        self.budgets.append(max_tokens)
        if len(self.budgets) == 1:
            return {
                "text": "Partial answer",
                "finish_reason": "length",
                "usage": {},
                "model": self.model,
            }
        return {
            "text": "Complete answer with all requested details.",
            "finish_reason": "stop",
            "usage": {},
            "model": self.model,
        }


@pytest.mark.asyncio
async def test_groq_truncation_retries_once_with_larger_token_budget():
    router = AIRouter(Settings())
    groq = TruncatedThenCompleteGroq()
    router.providers = {
        "nvidia": type("Unavailable", (), {"api_key": ""})(),
        "groq": groq,
        "gemini": type("Unavailable", (), {"api_key": ""})(),
        "openrouter": type("Unavailable", (), {"api_key": ""})(),
    }

    answer, provider, _ = await router.reply(
        [{"role": "user", "content": "Tell me about One Piece"}],
        "english",
    )

    assert provider == "groq"
    assert answer == "Complete answer with all requested details."
    assert len(groq.budgets) == 2
    assert groq.budgets[1] > groq.budgets[0]


def test_tenglish_instruction_requires_roman_script_only():
    instruction = AIRouter._language_instruction("tenglish")
    assert "Latin/Roman letters ONLY" in instruction
    assert "never Telugu Unicode script" in instruction
    assert "Do NOT answer in English with a few Telugu words added" in instruction
    assert "spoken Telangana Telugu sentence structure" in instruction


def test_provider_timeouts_leave_room_for_fallbacks():
    router = AIRouter(Settings())
    assert router._provider_timeout("nvidia", 1) == 5.0
    assert router._provider_timeout("groq", 1) == 7.0
    assert router._provider_timeout("gemini", 1) == 7.0
    assert router._provider_timeout("openrouter", 1) == 7.0
