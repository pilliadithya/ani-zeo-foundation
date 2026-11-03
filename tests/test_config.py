from app.config import Settings

def test_provider_order_parses():
    s=Settings(telegram_bot_token="test",webhook_secret="secret",database_url="postgresql://user:pass@localhost/db",ai_provider_order="gemini, groq,nvidia")
    assert s.provider_order == ["gemini","groq","nvidia"]
