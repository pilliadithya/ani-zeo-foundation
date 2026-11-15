import json

import pytest

from app.ai.research import AnimeResearchService
from app.ai.router import AIRouter


class Settings:
    provider_order = ["gemini", "groq"]
    ai_timeout_seconds = 1
    ai_total_timeout_seconds = 2
    ai_max_output_tokens = 300
    gemini_api_key = "test"
    gemini_model = "test-model"
    groq_api_key = ""
    groq_model = "test-model"
    nvidia_api_key = ""
    nvidia_model = "test-model"
    openrouter_api_key = ""
    openrouter_model = "test-model"


class FakeProvider:
    name = "gemini"
    api_key = "test"
    model = "test-model"
    fallback_api_keys = ()

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def generate(self, messages, timeout, max_tokens):
        if self.error:
            raise self.error
        return self.response


def test_unknown_intent_is_not_misclassified_as_off_topic():
    result = AnimeResearchService.detect_intent(
        "Can you explain this character to me?"
    )
    assert result["intent"] == "unclear"
    assert result["scope"] == "clarify"


def test_explicitly_unrelated_request_still_redirects():
    result = AnimeResearchService.detect_intent("Help me write Python code")
    assert result["intent"] == "off_topic"
    assert result["scope"] == "redirect"


@pytest.mark.asyncio
async def test_ai_intent_resolver_handles_unfamiliar_anime_entity():
    router = AIRouter(Settings())
    router.providers["gemini"] = FakeProvider(response=json.dumps({
        "intent": "character_question",
        "domain": "anime",
        "confidence": 0.94,
        "normalized_query": "Who is Itachi Uchiha?",
        "active_topic": "Itachi Uchiha",
        "resolved_entities": ["Itachi Uchiha"],
        "is_follow_up": False,
    }))
    result = await router.classify_intent("Tell me about Itachi Uchiha")
    assert result["intent"] == "character_question"
    assert result["scope"] == "anime"
    assert result["active_topic"] == "Itachi Uchiha"
    assert result["resolved_entities"] == ["Itachi Uchiha"]


@pytest.mark.asyncio
async def test_ai_intent_resolver_resolves_contextual_follow_up():
    router = AIRouter(Settings())
    router.providers["gemini"] = FakeProvider(response=json.dumps({
        "intent": "follow_up",
        "domain": "anime",
        "confidence": 0.91,
        "normalized_query": "Who is Luffy's mother in One Piece?",
        "active_topic": "One Piece",
        "resolved_entities": ["One Piece", "Luffy"],
        "is_follow_up": True,
    }))
    history = [
        {"role": "user", "content": "Tell me about One Piece"},
        {"role": "assistant", "content": "One Piece follows Luffy and his crew."},
    ]
    result = await router.classify_intent("What about his mother?", history, "tenglish")
    assert result["intent"] == "follow_up"
    assert result["normalized_text"] == "Who is Luffy's mother in One Piece?"
    assert result["context_used"] is True


@pytest.mark.asyncio
async def test_ai_intent_resolver_rejects_invalid_labels_and_fails_closed_to_clarify():
    router = AIRouter(Settings())
    router.providers["gemini"] = FakeProvider(response='{"intent":"run_shell","domain":"anime","confidence":1}')
    result = await router.classify_intent("Tell me about this")
    assert result is None


@pytest.mark.asyncio
async def test_ai_intent_resolver_does_not_redirect_low_confidence_off_topic():
    router = AIRouter(Settings())
    router.providers["gemini"] = FakeProvider(response=json.dumps({
        "intent": "unclear",
        "domain": "unclear",
        "confidence": 0.42,
        "normalized_query": "What do you mean?",
        "active_topic": None,
        "resolved_entities": [],
        "is_follow_up": False,
    }))
    result = await router.classify_intent("What do you mean?")
    assert result["scope"] == "clarify"


@pytest.mark.asyncio
async def test_ai_intent_resolver_provider_failure_returns_none():
    router = AIRouter(Settings())
    router.providers["gemini"] = FakeProvider(error=RuntimeError("provider offline"))
    assert await router.classify_intent("Tell me about this") is None
