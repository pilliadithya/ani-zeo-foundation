import asyncio
from dataclasses import dataclass, field
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class Provider:
    name: str
    api_key: str
    model: str
    base_url: str
    fallback_models: tuple[str, ...] = field(default_factory=tuple)
    fallback_api_keys: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def _usage_value(usage: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return None

    @classmethod
    def normalize_usage(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize common OpenAI-compatible usage fields without inventing missing values."""
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return {
                "input_tokens": None, "output_tokens": None, "total_tokens": None,
                "cached_input_tokens": None, "thinking_tokens": None,
                "tool_tokens": None, "raw_usage": None,
            }

        prompt_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        if not isinstance(prompt_details, dict):
            prompt_details = {}
        if not isinstance(completion_details, dict):
            completion_details = {}

        input_tokens = cls._usage_value(usage, "prompt_tokens", "input_tokens")
        output_tokens = cls._usage_value(usage, "completion_tokens", "output_tokens")
        total_tokens = cls._usage_value(usage, "total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        return {
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cached_input_tokens": cls._usage_value(prompt_details, "cached_tokens", "cache_read_input_tokens"),
            "thinking_tokens": cls._usage_value(completion_details, "reasoning_tokens", "thinking_tokens"),
            "tool_tokens": cls._usage_value(usage, "tool_use_prompt_tokens", "toolUsePromptTokenCount"),
            "raw_usage": usage,
        }

    async def generate(self, messages: list[dict], timeout: float, max_tokens: int) -> dict[str, Any]:
        keys = [self.api_key]
        if self.name in {"gemini", "groq"}:
            keys.extend(key for key in self.fallback_api_keys if key and key not in keys)
        if not any(keys):
            raise RuntimeError(f"{self.name} API key is not configured")
        if not self.model:
            raise RuntimeError(f"{self.name} model is not configured")

        models = [self.model]
        if self.name == "gemini":
            models.extend(model for model in self.fallback_models if model and model not in models)

        data = None
        selected_model = None
        last_error = None

        # Gemini account 1 is exhausted/invalid before trying account 2.
        # Each account gets the configured model fallback sequence. No quota bypass:
        # keys must belong to separately configured projects/accounts and obey their limits.
        for key_index, api_key in enumerate(keys):
            if not api_key:
                continue
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            if self.name == "openrouter":
                headers["X-Title"] = "Ani Zeo"

            account_succeeded = False
            # Give each configured account its own bounded window. Model fallbacks
            # share that account window so they cannot starve the next credential.
            account_deadline = time.monotonic() + max(0.1, float(timeout))
            log.info("%s account attempt account_position=%s model=%s",
                     self.name, key_index + 1, models[0])
            for model_index, model in enumerate(models):
                remaining_account = account_deadline - time.monotonic()
                if remaining_account <= 0.05:
                    log.warning("%s account window exhausted account_position=%s",
                                self.name, key_index + 1)
                    break
                request_timeout = min(float(timeout), remaining_account)
                payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
                # Gemini 3 models reject legacy sampling parameters such as temperature.
                if not (self.name == "gemini" and model.startswith("gemini-3")):
                    payload["temperature"] = 0.7

                try:
                    async with httpx.AsyncClient(timeout=request_timeout) as client:
                        # httpx timeouts are phase-based (connect/read/write/pool),
                        # not a strict wall-clock deadline. A slow trickling response
                        # can therefore outlive the account window. Enforce the
                        # remaining account budget around the complete request too.
                        response = await asyncio.wait_for(
                            client.post(
                                f"{self.base_url}/chat/completions",
                                headers=headers,
                                json=payload,
                            ),
                            timeout=request_timeout,
                        )
                        response.raise_for_status()
                        data = response.json()
                    selected_model = model
                    account_succeeded = True
                    if key_index:
                        log.info("%s secondary account succeeded account_position=%s", self.name, key_index + 1)
                    if model_index:
                        log.info("Gemini model fallback succeeded model=%s fallback_position=%s", model, model_index)
                    break
                except (asyncio.TimeoutError, httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if self.name in {"gemini", "groq"} and key_index < len(keys) - 1:
                        log.warning("%s account network failure account_position=%s (%s); trying secondary configured account",
                                    self.name, key_index + 1, type(exc).__name__)
                        break
                    raise
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if self.name == "gemini" and status in {429, 503} and model_index < len(models) - 1:
                        log.warning("Gemini model rate-limited/unavailable model=%s status=%s; trying configured model fallback", model, status)
                        continue
                    if self.name in {"gemini", "groq"} and status in {401, 403, 429, 500, 502, 503, 504} and key_index < len(keys) - 1:
                        log.warning("%s account unavailable account_position=%s status=%s; trying secondary configured account",
                                    self.name, key_index + 1, status)
                        break
                    raise
            if account_succeeded:
                break
            if self.name not in {"gemini", "groq"} or key_index >= len(keys) - 1:
                if last_error:
                    raise last_error

        if data is None or selected_model is None:
            if last_error:
                raise last_error
            raise RuntimeError(f"{self.name} exhausted its configured credential/model list")

        try:
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError(f"{self.name} returned no choices")
            choice = choices[0]
            message = choice.get("message")
            if not isinstance(message, dict):
                raise RuntimeError(f"{self.name} returned an invalid message")
            content = message.get("content")
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"{self.name} returned an unexpected response") from exc

        if content is None:
            raise RuntimeError(f"{self.name} returned null content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
            content = "".join(parts)
        if not isinstance(content, str):
            raise RuntimeError(f"{self.name} returned an unsupported content type")

        content = content.strip()
        if not content or content.lower() in {"none", "null"}:
            raise RuntimeError(f"{self.name} returned an empty response")

        return {
            "text": content,
            "usage": self.normalize_usage(data),
            "finish_reason": choice.get("finish_reason"),
            "model": data.get("model") or selected_model,
        }


def build_providers(settings):
    return {
        "gemini": Provider(
            "gemini",
            settings.gemini_api_key,
            settings.gemini_model,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            tuple(getattr(settings, "gemini_fallback_model_list", [])),
            tuple(getattr(settings, "gemini_api_key_list", [])[1:]),
        ),
        "groq": Provider(
            "groq", settings.groq_api_key, settings.groq_model,
            "https://api.groq.com/openai/v1",
            fallback_api_keys=tuple(getattr(settings, "groq_api_key_list", [])[1:]),
        ),
        "nvidia": Provider(
            "nvidia", settings.nvidia_api_key, settings.nvidia_model,
            "https://integrate.api.nvidia.com/v1",
        ),
        "openrouter": Provider(
            "openrouter", settings.openrouter_api_key, settings.openrouter_model,
            "https://openrouter.ai/api/v1",
        ),
    }
