import pytest

from app.ai.research import AnimeResearchService
from app.ai.router import AIRouter


def history(*messages):
    return [
        {"role": role, "content": content}
        for role, content in messages
    ]


DRAGON_HISTORY = history(
    ("user", "Luffy ki father evaru?"),
    ("assistant", "Luffy ki father Monkey D Dragon. He leads the Revolutionary Army."),
)


@pytest.mark.parametrize(
    "question, expected_intent",
    [
        ("Luffy ki powers enti?", "character_question"),
        ("Athani father evaru?", "follow_up"),
        ("Vaadiki Devil Fruit undha?", "character_question"),
        ("What about his weakness?", "character_question"),
        ("అతని పవర్స్ ఏంటి?", "character_question"),
        ("Inka konchem detail ga cheppu", "follow_up"),
    ],
)
def test_multilingual_followups_remain_in_anime_scope(question, expected_intent):
    result = AnimeResearchService.detect_intent(question, DRAGON_HISTORY)

    assert result["scope"] == "anime"
    assert result["intent"] == expected_intent
    assert result["is_follow_up"] is True
    assert result["context_used"] is True


def test_explicit_new_anime_topic_is_not_blocked_by_previous_topic():
    result = AnimeResearchService.detect_intent(
        "Tell me about Naruto",
        DRAGON_HISTORY,
    )

    assert result["scope"] == "anime"
    assert result["intent"] == "anime_question"
    assert result["is_follow_up"] is False


def test_followup_after_topic_switch_keeps_recent_anime_context():
    switched_history = DRAGON_HISTORY + history(
        ("user", "Tell me about Naruto"),
        ("assistant", "Naruto is the central character of the series."),
    )

    result = AnimeResearchService.detect_intent(
        "What are his powers?",
        switched_history,
    )

    assert result["scope"] == "anime"
    assert result["intent"] == "character_question"
    assert result["is_follow_up"] is True


def test_ambiguous_multi_character_history_is_preserved_for_writer():
    conversation = history(
        ("user", "Compare Luffy and Zoro."),
        ("assistant", "Luffy is a pirate captain; Zoro is his swordsman."),
        ("user", "What are their abilities?"),
    )
    router = AIRouter.__new__(AIRouter)
    messages = router._build_messages(
        conversation + history(("user", "What about his weakness?")),
        "english",
    )

    transcript = "\n".join(item["content"] for item in messages[1:])
    assert "Luffy" in transcript
    assert "Zoro" in transcript
    assert "What about his weakness?" in transcript


@pytest.mark.parametrize(
    "language, expected_instruction",
    [
        ("english", "casual conversational English"),
        ("telugu", "Tenglish"),
        ("tenglish", "Telangana-friendly spoken Tenglish"),
        ("hinglish", "Hinglish"),
        ("tanglish", "Tanglish"),
    ],
)
def test_contextual_followup_keeps_users_selected_response_language(
    language,
    expected_instruction,
):
    router = AIRouter.__new__(AIRouter)
    messages = router._build_messages(
        DRAGON_HISTORY + history(("user", "Athani powers cheppu")),
        language,
    )

    assert expected_instruction in messages[0]["content"]
    assert "Resolve references, follow-ups and" in messages[0]["content"]


def test_followup_without_anime_context_does_not_guess():
    result = AnimeResearchService.detect_intent(
        "Konchem athani power cheppa galava?",
        history(("user", "How are you?"), ("assistant", "I'm good.")),
    )

    assert result["scope"] == "redirect"


def test_unrelated_question_stays_out_of_scope_after_anime_conversation():
    result = AnimeResearchService.detect_intent(
        "Help me write Python code",
        DRAGON_HISTORY,
    )

    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"
