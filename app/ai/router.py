import logging
from app.ai.providers import build_providers
log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ani Zeo, a friendly AI anime companion. Be natural, helpful, spoiler-aware, and honest about uncertainty.
Do not invent anime titles, facts, citations, release dates, or personal experiences. If current information is required but no verified search results are provided, say you cannot verify it live.
Use the user's preferred language: Tenglish (Telugu-English in Latin script), Hinglish (Hindi-English in Latin script), Tanglish (Tamil-English in Latin script), or English. Follow explicit language switches. Do not overuse slang."""

class AIRouter:
    def __init__(self, settings):
        self.settings = settings
        self.providers = build_providers(settings)

    async def reply(self, history: list[dict], language: str | None = None):
        note = f"\nPreferred language: {language}." if language else ""
        messages = [{"role": "system", "content": SYSTEM_PROMPT + note}]
        for item in history[-12:]:
            if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
                messages.append({"role": item["role"], "content": item["content"][:12000]})
        failures = []
        for name in self.settings.provider_order:
            provider = self.providers.get(name)
            if not provider or not provider.api_key:
                continue
            try:
                return await provider.generate(messages, self.settings.ai_timeout_seconds, self.settings.ai_max_output_tokens), name
            except Exception as exc:
                log.warning("AI provider %s failed (%s)", name, type(exc).__name__)
                failures.append(name)
        if not failures:
            raise RuntimeError("No AI provider is configured. Add at least one API key.")
        raise RuntimeError("All configured AI providers failed: " + ", ".join(failures))
