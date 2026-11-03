from dataclasses import dataclass
import httpx

@dataclass
class Provider:
    name: str
    api_key: str
    model: str
    base_url: str

    async def generate(self, messages: list[dict], timeout: float, max_tokens: int) -> str:
        if not self.api_key:
            raise RuntimeError(f"{self.name} API key is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            headers["X-Title"] = "Ani Zeo"
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{self.name} returned an unexpected response") from exc
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = str(content).strip()
        if not content:
            raise RuntimeError(f"{self.name} returned an empty response")
        return content

def build_providers(settings):
    return {
      "gemini": Provider("gemini", settings.gemini_api_key, settings.gemini_model, "https://generativelanguage.googleapis.com/v1beta/openai"),
      "groq": Provider("groq", settings.groq_api_key, settings.groq_model, "https://api.groq.com/openai/v1"),
      "nvidia": Provider("nvidia", settings.nvidia_api_key, settings.nvidia_model, "https://integrate.api.nvidia.com/v1"),
      "openrouter": Provider("openrouter", settings.openrouter_api_key, settings.openrouter_model, "https://openrouter.ai/api/v1"),
    }
