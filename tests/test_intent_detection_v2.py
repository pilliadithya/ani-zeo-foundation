import pytest

from app.ai.research import AnimeResearchService


def history(*items):
    return [{"role": role, "content": text} for role, text in items]


ONE_PIECE = history(
    ("user", "Luffy ki father evaru?"),
    ("assistant", "Luffy ki father Monkey D Dragon. He leads the Revolutionary Army."),
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Luffy ki powers enti?", "character_question"),
        ("Athani father evaru?", "follow_up"),
        ("Vaadiki Devil Fruit undha?", "character_question"),
        ("What about his weakness?", "character_question"),
        ("అతని పవర్స్ ఏంటి?", "character_question"),
        ("Inka konchem detail ga cheppu", "follow_up"),
        ("Edo tensei ante", "follow_up"),
        ("Ante enti?", "follow_up"),
        ("Bro in Telugu", "follow_up"),
    ],
)
def test_multilingual_followups_keep_anime_scope(question, expected):
    context = ONE_PIECE
    if question in {"Edo tensei ante", "Ante enti?"}:
        context = history(
            ("user", "Naruto lo Edo Tensei technique gurinchi cheppu"),
            ("assistant", "Edo Tensei is a reanimation technique in Naruto."),
        )
    result = AnimeResearchService.detect_intent(question, context)
    assert result["scope"] == "anime"
    assert result["intent"] == expected
    assert result["is_follow_up"] is True
    assert result["context_used"] is True


def test_explicit_new_anime_topic_replaces_previous_topic():
    result = AnimeResearchService.detect_intent("Tell me about Naruto", ONE_PIECE)
    assert result["scope"] == "anime"
    assert result["intent"] == "anime_question"
    assert result["is_follow_up"] is False


def test_latest_topic_is_used_for_followup_after_topic_switch():
    conversation = ONE_PIECE + history(
        ("user", "Tell me about Naruto"),
        ("assistant", "Naruto is a shinobi from Konoha."),
    )
    result = AnimeResearchService.detect_intent("What are his powers?", conversation)
    assert result["scope"] == "anime"
    assert result["intent"] == "character_question"
    assert result["is_follow_up"] is True


def test_old_anime_context_does_not_capture_followup_after_offtopic_turn():
    conversation = ONE_PIECE + history(
        ("user", "Help me write Python code"),
        ("assistant", "Sure, what should the code do?"),
    )
    result = AnimeResearchService.detect_intent("Explain it more", conversation)
    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"


def test_synthetic_active_topic_does_not_override_latest_offtopic_user_turn():
    conversation = history(
        ("user", "Tell me about One Piece"),
        ("assistant", "One Piece is a pirate adventure."),
        ("user", "Help me write Python code"),
        ("assistant", "Ani Zeo active conversation topic: One Piece"),
    )
    result = AnimeResearchService.detect_intent("Explain it more", conversation)
    assert result["scope"] == "redirect"


def test_offtopic_request_wins_even_when_old_anime_context_exists():
    result = AnimeResearchService.detect_intent("Help me write Python code", ONE_PIECE)
    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"


def test_ambiguous_pronoun_without_context_requests_clarification():
    result = AnimeResearchService.detect_intent(
        "Konchem athani power cheppa galava?",
        history(("user", "How are you?"), ("assistant", "I'm good.")),
    )
    assert result["scope"] == "clarify"
    assert result["context_used"] is False


def test_weather_question_is_not_captured_by_anime_context():
    result = AnimeResearchService.detect_intent("What's the weather today?", ONE_PIECE)
    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"


def test_character_question_without_named_entity_uses_recent_anime_context():
    result = AnimeResearchService.detect_intent("What is his weakness?", ONE_PIECE)
    assert result["intent"] == "character_question"
    assert result["scope"] == "anime"


def test_anime_title_lookup_still_routes_to_metadata_flow():
    result = AnimeResearchService.detect_intent("Tell me about One Piece")
    assert result["intent"] == "anime_question"
    assert result["scope"] == "anime"
    assert AnimeResearchService.extract_title("Tell me about One Piece") == "One Piece"


@pytest.mark.parametrize(
    "question",
    [
        "Who is Itachi Uchiha?",
        "Who is Kakashi Hatake?",
        "Who is Madara Uchiha?",
        "Who are the Akatsuki?",
    ],
)
def test_fresh_character_questions_do_not_require_allowlisted_entities(question):
    result = AnimeResearchService.detect_intent(question)
    assert result["intent"] == "character_question"
    assert result["scope"] == "anime"
    assert AnimeResearchService.extract_title(question) is None


@pytest.mark.parametrize("question", ["Itachi evaru?", "Itachi Uchiha ఎవరు?"])
def test_tenglish_and_telugu_character_questions_are_in_scope(question):
    result = AnimeResearchService.detect_intent(question)
    assert result["intent"] == "character_question"
    assert result["scope"] == "anime"


def test_explicit_offtopic_still_wins_over_character_question_shape():
    result = AnimeResearchService.detect_intent("Who is Python and how do I code with it?")
    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Give me its traler", "Give me its trailer"),
        ("Tell me about anmie", "Tell me about anime"),
        ("What is the narutoo release date?", "What is the Naruto release date?"),
        ("Show me the latest episdoe", "Show me the latest episode"),
        ("Give me its charecter list", "Give me its character list"),
        ("Tell me Kaijuu No. 8 details", "Tell me Kaiju No. 8 details"),
    ],
)
def test_common_anime_typing_errors_are_corrected(message, expected):
    assert AnimeResearchService.correct_typos(message) == expected


def test_typo_correction_does_not_rewrite_unfamiliar_proper_nouns():
    message = "Tell me about Xylar Venn"
    assert AnimeResearchService.correct_typos(message) == message


def test_typo_corrected_followup_keeps_anime_intent():
    conversation = history(
        ("user", "Tell me about Kaiju No. 8"),
        ("assistant", "Kaiju No. 8 is an anime about the Defense Force."),
    )
    result = AnimeResearchService.detect_intent("Give me its traler", conversation)
    assert result["normalized_text"] == "Give me its trailer"
    assert result["intent"] == "follow_up"
    assert result["scope"] == "anime"
