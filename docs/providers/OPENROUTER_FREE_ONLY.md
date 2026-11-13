# OpenRouter — Free Models Only

Status: **Reserved for activation after the owner adds the API key**

## Mandatory policy

- Use the OpenRouter free-model route: `openrouter/free`.
- Do not select paid model IDs.
- Do not add credits, enable paid routing, or silently fall back to paid models.
- Keep OpenRouter disabled when the API key is missing.
- Treat provider rate limits and free-model availability as normal transient failures.
- If no eligible free model is available, continue to the next explicitly configured provider or use the existing safe failure response.
- Never expose API keys in logs, Telegram messages, or telemetry.

## Validation before enabling

1. Confirm the key is present without printing its value.
2. Send a small test request explicitly through `openrouter/free`.
3. Verify the returned model/provider metadata indicates a free route.
4. Verify that rate-limit, unavailable-model, timeout, and empty-response cases do not trigger paid routing.
5. Add automated tests proving that no paid model ID can be selected by the OpenRouter adapter.

## Limits

Free-tier request quotas and model availability can change. Do not hard-code a historical daily request allowance as a guarantee; inspect the current OpenRouter account and official limits at activation time.
