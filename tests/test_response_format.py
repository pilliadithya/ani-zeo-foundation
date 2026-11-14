"""Regression tests for Ani Zeo intent-aware presentation traits."""

from app.ai.research import AnimeResearchService
from app.main import apply_emoji_style, enforce_response_format


def test_comparison_intent_is_classified():
    result = AnimeResearchService.detect_intent("Compare Naruto vs One Piece")
    assert result["intent"] == "comparison"
    assert result["scope"] == "anime"


def test_episode_and_chapter_intents_are_classified():
    episode = AnimeResearchService.detect_intent("Explain One Piece episode 1071")
    chapter = AnimeResearchService.detect_intent("What happened in Naruto chapter 700?")
    assert episode["intent"] == "episode_chapter"
    assert chapter["intent"] == "episode_chapter"


def test_comparison_receives_compact_structured_title_without_losing_content():
    answer = enforce_response_format("Naruto focuses on ninja conflict.\\nOne Piece focuses on adventure.", "comparison")
    assert answer.startswith("**⚖️ ANIME COMPARISON**")
    assert "Naruto focuses" in answer and "One Piece focuses" in answer


def test_episode_chapter_receives_spoiler_aware_layout_title():
    answer = enforce_response_format("The episode adapts the battle.", "episode_chapter")
    assert answer.startswith("**📖 STORY / EPISODE BREAKDOWN**")


def test_follow_up_stays_contextual_without_forced_editorial_title():
    answer = enforce_response_format("That refers to his older brother.", "follow_up")
    assert answer == "That refers to his older brother."


def test_emoji_style_does_not_inject_japanese_flag():
    answer = apply_emoji_style("Here is the anime profile.", "anime_question")
    assert "🎌" not in answer
    assert answer.startswith("🌟 ")
