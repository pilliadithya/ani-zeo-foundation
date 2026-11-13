from app.config import Settings


def test_provider_order_parses():
    s = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
        ai_provider_order="nvidia, groq, gemini, openrouter",
    )
    assert s.provider_order == ["gemini", "groq"]


def test_default_ai_fallback_order_is_gemini_then_groq_only():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
    )
    assert settings.provider_order == ["gemini", "groq"]


def test_gemini_account_keys_are_separate_and_deduplicated():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
        gemini_api_key="primary",
        gemini_api_key_2="secondary",
    )
    assert settings.gemini_api_key_list == ["primary", "secondary"]


def test_groq_account_keys_are_separate_and_deduplicated():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
        groq_api_key="groq-primary",
        groq_api_key_2="groq-secondary",
    )
    assert settings.groq_api_key_list == ["groq-primary", "groq-secondary"]


def test_search_provider_order_is_configurable_and_validated():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
        search_provider_order="langsearch,decodo,tavily,unknown",
    )
    assert settings.search_order == ["langsearch", "decodo", "tavily"]
