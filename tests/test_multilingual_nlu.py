from app.ai.research import AnimeResearchService


def dragon_conversation():
    return [
        {"role": "user", "content": "Luffy ki father evaru?"},
        {
            "role": "assistant",
            "content": (
                "Luffy ki father Monkey D Dragon. Series lo World Government ki "
                "rebel leader ga chupincharu."
            ),
        },
    ]


def test_romanized_telugu_character_followup_resolves_anime_scope():
    result = AnimeResearchService.detect_intent(
        "Konchem anthani power cheppa galava?",
        dragon_conversation(),
    )
    assert result["scope"] == "anime"
    assert result["intent"] == "character_question"
    assert result["is_follow_up"] is True
    assert result["context_used"] is True


def test_romanized_telugu_short_continuation_keeps_previous_anime_topic():
    result = AnimeResearchService.detect_intent(
        "Inka konchem detail ga cheppu",
        dragon_conversation(),
    )
    assert result["scope"] == "anime"
    assert result["intent"] == "follow_up"


def test_telugu_script_character_followup_is_recognized():
    result = AnimeResearchService.detect_intent(
        "అతని పవర్స్ చెప్పగలవా?",
        dragon_conversation(),
    )
    assert result["scope"] == "anime"
    assert result["intent"] == "character_question"


def test_english_followup_behavior_is_preserved():
    result = AnimeResearchService.detect_intent(
        "What about his weakness?",
        dragon_conversation(),
    )
    assert result["scope"] == "anime"
    assert result["intent"] == "character_question"


def test_pronoun_without_anime_context_does_not_guess_a_subject():
    result = AnimeResearchService.detect_intent(
        "Konchem athani power cheppa galava?",
        [{"role": "user", "content": "How are you?"}],
    )
    assert result["scope"] == "redirect"


def test_unrelated_request_is_not_misclassified_from_old_anime_context():
    result = AnimeResearchService.detect_intent(
        "Help me write Python code",
        dragon_conversation(),
    )
    assert result["scope"] == "redirect"
    assert result["intent"] == "off_topic"
