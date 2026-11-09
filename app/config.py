from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    telegram_bot_token: str
    webhook_secret: str
    database_url: str
    ai_provider_order: str = "gemini,groq,openrouter"
    ai_timeout_seconds: float = 25
    ai_max_output_tokens: int = 700
    ai_cost_rates_json: str = "{}"
    ai_usage_admin_ids: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    tavily_api_key: str = ""
    decodo_api_key: str = ""
    langsearch_api_key: str = ""
    search_provider_order: str = "decodo,langsearch,tavily"
    decodo_geo: str = "IN"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.0-flash-001"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def provider_order(self) -> list[str]:
        return [p.strip().lower() for p in self.ai_provider_order.split(",") if p.strip()]

    @property
    def search_order(self) -> list[str]:
        allowed = {"decodo", "langsearch", "tavily"}
        return [p.strip().lower() for p in self.search_provider_order.split(",") if p.strip().lower() in allowed]

@lru_cache
def get_settings() -> Settings:
    return Settings()
