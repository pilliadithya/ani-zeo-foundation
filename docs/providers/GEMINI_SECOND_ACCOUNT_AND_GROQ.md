# AI provider setup — Gemini account 1 + account 2 + Groq

Active default provider order: **Gemini → Groq**.

## Render environment variables

Required for primary Gemini:
- `GEMINI_API_KEY`

Optional second Gemini account:
- `GEMINI_API_KEY_2`

Groq fallback:
- `GROQ_API_KEY`
- `GROQ_API_KEY_2` (optional second Groq account)
- `GROQ_MODEL`

OpenRouter is intentionally excluded from the active default order for now. Its adapter/configuration remains dormant; do not add it to `AI_PROVIDER_ORDER` until the operator asks to activate it. Bytez remains a documented placeholder only.

## Gemini account fallback behavior

The Gemini adapter tries account 1 first. It uses the configured Gemini model and, on quota/service responses (429/503), its configured model fallback list. If the account is still unavailable, it can try account 2 using the same model sequence. Invalid/permission responses (401/403) can also move to account 2.

Use account 2 only when it is legitimately a separate Google AI Studio / Google Cloud project with its own applicable quota and terms. Do not create or rotate keys to evade rate limits. The application does not distribute ordinary requests across accounts; it fails over only after an eligible error.

Groq account 1 is also tried before the optional `GROQ_API_KEY_2` account on eligible authentication, quota, or temporary service errors. Both account slots must follow their own provider terms; this is failure recovery, not request rotation.

## Provider-level fallback

If Gemini accounts/models cannot produce a valid answer, the existing router can continue to Groq according to the configured provider order. Groq remains the second provider, not a Gemini API key.

## Safe setup

1. Add `GEMINI_API_KEY_2` privately in Render when the second account is ready.
2. Never paste keys into chat, GitHub, logs, or screenshots.
3. Confirm the variable name is present without revealing its value.
4. Test the primary Gemini path, secondary-account failover, then Groq fallback.
5. Keep Render auto-deploy disabled; deployment requires separate approval.

No production deployment or Render environment change is performed by this code preparation.
