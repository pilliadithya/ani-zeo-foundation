import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://unused")

from app.main import (
    enforce_response_format,
    markdown_to_telegram_html,
    split_text_safely,
)


def test_each_structured_intent_gets_appropriate_editorial_title():
    cases = {
        "live_news": "ANIME NEWS",
        "anime_question": "ANIME GUIDE",
        "watch_order": "WATCH / READ ORDER",
        "recommendation": "RECOMMENDATIONS",
        "industry_question": "INDUSTRY INSIGHT",
        "follow_up": "CONTINUING THE DISCUSSION",
    }
    for intent, title in cases.items():
        rendered = enforce_response_format("A useful answer.", intent)
        assert title in rendered
        assert "A useful answer." in rendered
    assert "CHARACTER DOSSIER" not in enforce_response_format("Luffy's father is Dragon.", "character_question")


def test_existing_model_title_is_not_duplicated():
    rendered = enforce_response_format("**My Anime Report**\n\nA useful answer.", "live_news")
    assert rendered.count("My Anime Report") == 1
    assert "ANIME NEWS" not in rendered


def test_casual_answer_is_not_forced_into_an_article_template():
    rendered = enforce_response_format("Hey! What's up?", "greeting")
    assert rendered == "Hey! What's up?"


def test_heading_normalisation_and_excessive_blank_lines():
    rendered = enforce_response_format("### Overview\n\n\nThe story begins.")
    assert "**Overview**" in rendered
    assert "\n\n\n" not in rendered


def test_telegram_html_escapes_untrusted_text_and_converts_markdown():
    rendered = markdown_to_telegram_html("**Title**\n\n<script>alert(1)</script>\n- One Piece")
    assert "<b>Title</b>" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "• One Piece" in rendered


def test_markdown_table_becomes_mobile_friendly_labelled_bullets():
    source = "| Arc | Episodes |\n|---|---|\n| East Blue | 1-61 |"
    rendered = markdown_to_telegram_html(source)
    assert "Arc:" in rendered
    assert "Episodes:" in rendered
    assert "East Blue" in rendered


def test_long_responses_split_under_telegram_chunk_limit():
    chunks = split_text_safely(("A useful sentence.\n\n" * 300), limit=3500)
    assert len(chunks) > 1
    assert all(len(chunk) <= 3500 for chunk in chunks)
