from app.ai.router import AIRouter, SYSTEM_PROMPT
from app.ai.research import AnimeResearchService


class PromptSettings:
    provider_order = []
    ai_timeout_seconds = 1
    ai_max_output_tokens = 100
    gemini_api_key = ""
    gemini_model = "test"
    groq_api_key = ""
    groq_model = "test"
    nvidia_api_key = ""
    nvidia_model = "test"
    openrouter_api_key = ""
    openrouter_model = "test"


def test_telegram_editorial_style_is_mandatory_and_compact():
    assert "Telegram-first editorial rules" in SYSTEM_PROMPT
    assert "short 1–3-line paragraphs" in SYSTEM_PROMPT
    assert "never send a wall of text" in SYSTEM_PROMPT
    assert "TELEGRAM STYLE EXAMPLE" in SYSTEM_PROMPT
    messages = AIRouter(PromptSettings())._build_messages([{"role": "user", "content": "Hi"}], "english")
    assert AIRouter.estimate_messages_tokens(messages) < 1_300


def test_card_style_example_does_not_promise_fake_controls():
    assert "**🎴 Chainsaw Man**" in SYSTEM_PROMPT
    assert "only when the bot implements them" in SYSTEM_PROMPT


def test_artwork_and_trailer_links_must_be_grounded():
    assert "never invent image links" in SYSTEM_PROMPT
    assert "labelled as searches, not verified official videos" in SYSTEM_PROMPT


def test_naruto_classic_title_is_a_valid_anime_request():
    result = AnimeResearchService.detect_intent("Tell me about Naruto classic")
    assert result["scope"] == "anime"
    assert result["intent"] == "anime_question"
