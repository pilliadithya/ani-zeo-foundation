from app.ai.router import SYSTEM_PROMPT
from app.ai.research import AnimeResearchService


def test_telegram_editorial_style_is_mandatory_and_mobile_first():
    assert "mobile editorial card" in SYSTEM_PROMPT
    assert "short paragraphs" in SYSTEM_PROMPT
    assert "Never output raw HTML" in SYSTEM_PROMPT
    assert "TELEGRAM STYLE EXAMPLES" in SYSTEM_PROMPT


def test_character_answers_use_artwork_only_when_app_supplies_it():
    assert "include character artwork when the app supplies it" in SYSTEM_PROMPT
    assert "do not invent image links" in SYSTEM_PROMPT


def test_naruto_classic_title_is_a_valid_anime_request():
    result = AnimeResearchService.detect_intent("Tell me about Naruto classic")
    assert result["scope"] == "anime"
    assert result["intent"] == "anime_question"
