from app.handlers import LANGUAGES, language_keyboard, normalise_display_name


def test_language_choices_match_configured_bot_languages():
    assert [code for _, code in LANGUAGES] == [
        "tenglish",
        "hinglish",
        "tanglish",
        "english",
    ]


def test_language_keyboard_uses_no_country_flags():
    keyboard = language_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [button.callback_data for button in buttons] == [
        "lang:tenglish",
        "lang:hinglish",
        "lang:tanglish",
        "lang:english",
    ]
    assert all(not any(ord(char) in range(0x1F1E6, 0x1F200) for char in button.text) for button in buttons)


def test_display_name_is_trimmed_and_whitespace_is_normalised():
    assert normalise_display_name("  Anime   Monarch  ") == "Anime Monarch"


def test_display_name_allows_user_selected_script():
    assert normalise_display_name("Adithya") == "Adithya"
    assert normalise_display_name("山田") == "山田"


def test_display_name_rejects_empty_and_overlong_values():
    assert normalise_display_name("   ") is None
    assert normalise_display_name("x" * 41) is None
