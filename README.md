# Ani Zeo — foundation build

Python Telegram AI companion using FastAPI webhooks, Supabase PostgreSQL, and configurable AI providers. This is milestone 1, not a claim that every planned feature is complete.

## Stack
- Python 3.11+
- FastAPI + Uvicorn
- python-telegram-bot
- Supabase PostgreSQL through asyncpg
- Gemini, Groq, NVIDIA NIM and OpenRouter provider adapters
- pytest

## Setup
1. Create a Python 3.11+ environment and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`; fill in credentials locally. Never commit real secrets.
3. Run `database/schema.sql` in the Supabase SQL Editor. For an existing deployment, run new files in `database/migrations/` in order (including `005_minimal_onboarding_step.sql` before deploying this onboarding change).
4. Run locally with `uvicorn app.main:app --reload`.
5. Configure Telegram webhook to `https://YOUR_PUBLIC_HTTPS_HOST/telegram/webhook` and set the same `WEBHOOK_SECRET` in Render and the webhook's `secret_token` parameter.
6. Render build command: `pip install -r requirements.txt`; start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
7. Add secrets in Render's environment settings. Do not paste bot tokens or API keys into chat or source control.

Example webhook setup (replace values locally; don't share the resulting URL):
`https://api.telegram.org/bot<TOKEN>/setWebhook?url=https%3A%2F%2FYOUR_HOST%2Ftelegram%2Fwebhook&secret_token=<URL_ENCODED_SECRET>`

## Live search providers

The live anime research path uses Gemini Google Search grounding first, then the configured sequential search fallback chain. Configure optional keys in the server environment:
- `DECODO_API_KEY`
- `LANGSEARCH_API_KEY`
- `TAVILY_API_KEY`
- `SEARCH_PROVIDER_ORDER=decodo,langsearch,tavily` (default)
- `DECODO_GEO=IN` (default country targeting)

Each provider is normalised into the same evidence pipeline. Results without usable HTTPS sources or clear anime relevance are rejected. Provider keys are optional; unavailable or exhausted providers are skipped and the next configured provider is tried. Live API behaviour must still be verified with the user's own provider accounts after deployment.

## Free-tier note
The project targets free tiers, not unlimited usage. Provider quotas, cold starts, inactive-project pauses, and plan changes can affect uptime. Test live provider calls after adding keys.

## Current scope
Webhook health check, compact welcome/disclaimer onboarding, user-chosen display name, language choice, automatic Telegram numeric ID, persistent profile and conversation messages, `/newchat`, `/settings`, `/privacy`, data deletion confirmation, AI provider fallback, Gemini grounding, and configurable Decodo/LangSearch/Tavily search adapters with shared evidence filtering. Live provider quota/credential verification, full anime search/recommendations, advanced adaptive memory, legal review, and production end-to-end tests remain outstanding.
