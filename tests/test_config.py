from app.config import Settings

def test_provider_order_parses():
    s=Settings(telegram_bot_token="test",webhook_secret="secret",database_url="postgresql://user:pass@localhost/db",ai_provider_order="gemini, groq,nvidia")
    assert s.provider_order == ["gemini","groq","nvidia"]


def test_default_ai_fallback_includes_nvidia():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
    )
    assert settings.provider_order == ["gemini", "nvidia", "groq", "openrouter"]


def test_search_provider_order_is_configurable_and_validated():
    settings = Settings(
        telegram_bot_token="test",
        webhook_secret="secret",
        database_url="postgresql://user:pass@localhost/db",
        search_provider_order="langsearch,decodo,tavily,unknown",
    )
    assert settings.search_order == ["langsearch", "decodo", "tavily"]
