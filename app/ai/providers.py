
from dataclasses import dataclass
import logging

import httpx


log = logging.getLogger(__name__)


@dataclass
class Provider:
    name: str
    api_key: str
    model: str
    base_url: str

    async def generate(
        self,
        messages: list[dict],
        timeout: float,
        max_tokens: int
    ) -> str:

        if not self.api_key:
            raise RuntimeError(
                f"{self.name} API key is not configured"
            )

        if not self.model:
            raise RuntimeError(
                f"{self.name} model is not configured"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.name == "openrouter":
            headers["X-Title"] = "Ani Zeo"

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            response.raise_for_status()
            data = response.json()

        if self.name == "nvidia":
            choices = data.get("choices") if isinstance(data, dict) else None
            first = choices[0] if isinstance(choices, list) and choices else {}
            message = first.get("message") if isinstance(first, dict) else {}
            message = message if isinstance(message, dict) else {}
            usage = data.get("usage") if isinstance(data, dict) else {}
            usage = usage if isinstance(usage, dict) else {}
            log.info(
                "NVIDIA response metadata (model=%s, choices=%s, "
                "finish_reason=%s, content_type=%s, has_reasoning_content=%s, "
                "prompt_tokens=%s, completion_tokens=%s)",
                self.model,
                len(choices) if isinstance(choices, list) else 0,
                first.get("finish_reason") if isinstance(first, dict) else None,
                type(message.get("content")).__name__,
                bool(message.get("reasoning_content")),
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )

        try:
            choices = data.get("choices")

            if not isinstance(choices, list) or not choices:
                raise RuntimeError(
                    f"{self.name} returned no choices"
                )

            message = choices[0].get("message")

            if not isinstance(message, dict):
                raise RuntimeError(
                    f"{self.name} returned an invalid message"
                )

            content = message.get("content")

        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(
                f"{self.name} returned an unexpected response"
            ) from exc

        # Never convert None into the literal string "None".
        if content is None:
            raise RuntimeError(
                f"{self.name} returned null content"
            )

        # Handle providers that return text in content blocks.
        if isinstance(content, list):
            parts = []

            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")

                    if isinstance(text, str) and text.strip():
                        parts.append(text)

            content = "".join(parts)

        if not isinstance(content, str):
            raise RuntimeError(
                f"{self.name} returned an unsupported content type"
            )

        content = content.strip()

        if not content or content.lower() in {"none", "null"}:
            raise RuntimeError(
                f"{self.name} returned an empty response"
            )

        return content


def build_providers(settings):
    return {
        "gemini": Provider(
            "gemini",
            settings.gemini_api_key,
            settings.gemini_model,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),

        "groq": Provider(
            "groq",
            settings.groq_api_key,
            settings.groq_model,
            "https://api.groq.com/openai/v1",
        ),

        "nvidia": Provider(
            "nvidia",
            settings.nvidia_api_key,
            settings.nvidia_model,
            "https://integrate.api.nvidia.com/v1",
        ),

        "openrouter": Provider(
            "openrouter",
            settings.openrouter_api_key,
            settings.openrouter_model,
            "https://openrouter.ai/api/v1",
        ),
    }
