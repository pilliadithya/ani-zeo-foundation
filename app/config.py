from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    telegram_bot_token: str
    webhook_secret: str
    database_url: str
    ai_provider_order: str = "gemini,groq"
    ai_timeout_seconds: float = 12
    ai_total_timeout_seconds: float = 28
    ai_max_output_tokens: int = 1400
    # Allow a single Groq retry with a larger completion budget after finish_reason=length.
    ai_groq_retry_max_output_tokens: int = 1800
    ai_cost_rates_json: str = "{}"
    ai_usage_admin_ids: str = ""
    gemini_api_key: str = ""
    # Optional second, independently-owned Gemini account/project key.
    gemini_api_key_2: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Comma-separated Gemini model fallbacks, tried only after HTTP 429/503.
    gemini_fallback_models: str = "gemini-3.5-flash-lite,gemini-3.7-flash,gemini-3.6-flash,gemini-3.8-flash"
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
    def gemini_fallback_model_list(self) -> list[str]:
        primary = self.gemini_model.strip()
        models = [model.strip() for model in self.gemini_fallback_models.split(",") if model.strip()]
        return list(dict.fromkeys(model for model in models if model != primary))

    @property
    def gemini_api_key_list(self) -> list[str]:
        return list(dict.fromkeys(
            key.strip() for key in (self.gemini_api_key, self.gemini_api_key_2) if key.strip()
        ))

    @property
    def search_order(self) -> list[str]:
        allowed = {"decodo", "langsearch", "tavily"}
        return [p.strip().lower() for p in self.search_provider_order.split(",") if p.strip().lower() in allowed]

@lru_cache
def get_settings() -> Settings:
    return Settings()
