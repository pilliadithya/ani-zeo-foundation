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

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.handlers import start, handle_onboarding_name, greeting_for_language


class FakeOnboardingDatabase:
    def __init__(self, profile):
        self.profile = profile
        self.saved_name = None
        self.step = None
        self.ensure_calls = []

    async def ensure_profile(self, user_id, username=None, display_name=None):
        self.ensure_calls.append((user_id, username, display_name))

    async def get_profile(self, user_id):
        return self.profile

    async def set_display_name(self, user_id, display_name):
        self.saved_name = (user_id, display_name)

    async def set_onboarding_step(self, user_id, step):
        self.step = (user_id, step)


@pytest.mark.asyncio
async def test_start_shows_creator_credit_and_disclaimer_in_one_welcome_note():
    db = FakeOnboardingDatabase({"onboarding_step": "welcome"})
    message = MagicMock()
    message.reply_text = AsyncMock()
    user = MagicMock(id=123, username="should_not_be_saved", first_name="Nakama")
    update = MagicMock(effective_user=user, effective_message=message)
    context = MagicMock()
    context.application.bot_data = {"db": db}

    await start(update, context)

    welcome = message.reply_text.await_args.args[0]
    assert "Anime Monarch" in welcome
    assert "prototype" in welcome
    assert "AI notice" in welcome
    assert "Privacy" in welcome
    assert "🇮🇳" not in welcome and "🇬🇧" not in welcome
    assert message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "consent:yes"
    assert db.ensure_calls == []  # ID is persisted only after the user accepts the welcome notice.


@pytest.mark.asyncio
async def test_name_message_saves_only_the_user_chosen_name_and_moves_to_language():
    db = FakeOnboardingDatabase({"onboarding_step": "awaiting_name"})
    message = MagicMock(text="  Anime   Monarch  ")
    message.reply_text = AsyncMock()
    user = MagicMock(id=456)
    update = MagicMock(effective_user=user, effective_message=message)
    context = MagicMock()
    context.application.bot_data = {"db": db}

    handled = await handle_onboarding_name(update, context)

    assert handled is True
    assert db.saved_name == (456, "Anime Monarch")
    assert db.step == (456, "awaiting_language")
    assert message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "lang:tenglish"


@pytest.mark.parametrize("language", ["english", "tenglish", "hinglish", "tanglish"])
def test_greetings_are_varied_and_use_romanised_language(language):
    first = greeting_for_language(language)
    second = greeting_for_language(language, previous=first)

    assert first != second
    assert not any(0x1F1E6 <= ord(char) <= 0x1F1FF for char in first)
    assert not any(0x0900 <= ord(char) <= 0x0DFF for char in first)


def test_greeting_supports_pirate_flag_but_never_requires_country_flags():
    greetings = [greeting_for_language("english") for _ in range(20)]
    assert all(not any(0x1F1E6 <= ord(char) <= 0x1F1FF for char in item) for item in greetings)
