# Ani Zeo — Master Architecture & Integration Roadmap

**Status:** Architecture baseline for the rebuild  
**Base:** `feature/minimal-multilingual-onboarding` at `816a3064c1da52004e6a39af04f278eea9f2c526`  
**Working branch:** `rebuild/master-architecture-v1`  
**Deployment policy:** Render auto-deploy remains disabled. This branch is not production deployment approval.

## 1. Product objective

Ani Zeo is a Telegram-first anime and manga discovery companion. It should behave like a useful anime friend while keeping factual answers evidence-backed, current when freshness matters, consistent in formatting, privacy-aware, efficient with free-tier resources, and independent of any single AI vendor or coding assistant.

## 2. Core engineering principle

Build for the future; activate only what is needed now; expand capacity and integrations when real usage or a defined product requirement justifies them.

Every integration must be replaceable, observable, testable, and independently disableable. Do not add providers merely to increase provider count.

## 3. Current repository baseline

The deployed foundation branch contains:
- FastAPI Telegram webhook application and handlers.
- Supabase/PostgreSQL persistence and additive migrations.
- AI routing for Gemini, Groq, NVIDIA and OpenRouter.
- Gemini model fallback configuration.
- Shared AI response/presentation instructions and Tenglish handling.
- Anime research, live-search adapters, evidence filtering and a fact-verification layer.
- AniList GraphQL and Jikan anime metadata access.
- AI usage telemetry and admin usage reporting.
- Webhook idempotency, onboarding, privacy/settings flows and automated tests.

The deployed Render service is connected to this repository and branch, with auto-deploy disabled. Preserve the current production service and existing database data during rebuild work.

## 4. Integration inventory

### 4.1 AI model providers

| Provider | Environment key | Current code status | Role |
|---|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | Implemented | Primary-capable model and Google Search grounding |
| Groq | `GROQ_API_KEY` | Implemented | Model fallback |
| NVIDIA NIM | `NVIDIA_API_KEY` | Implemented | Model fallback |
| OpenRouter | `OPENROUTER_API_KEY` | Implemented | Model fallback / model access |
| Bytez | Not defined yet | Not implemented | Evaluate API compatibility before adding |

The four implemented providers use a common provider adapter pattern. Bytez must not be treated as integrated until its official API contract, supported models, usage limits, terms and free access are verified and an adapter plus tests are implemented.

### 4.2 Search and grounding providers

| Provider | Environment key | Current code status | Role |
|---|---|---|---|
| Decodo Web Data API | `DECODO_API_KEY` | Implemented | Search fallback |
| LangSearch | `LANGSEARCH_API_KEY` | Implemented | Search fallback |
| Tavily | `TAVILY_API_KEY` | Implemented | Search fallback |
| Gemini Google Search grounding | Uses `GEMINI_API_KEY` | Present in research path | First live-grounding path |

Current configured search fallback order is `decodo,langsearch,tavily`. Do not add another search vendor yet. First measure the existing three for relevance, latency, source quality, quota, failure rate and free-tier fit. Reserve extension capacity in the architecture, but add another search key only if evidence shows a material gap.

Decodo's current Web Data API describes /search, /scrape, /map and /crawl under one key; the existing Ani Zeo adapter must be audited against the currently used endpoint and response schema before any migration. Do not assume an existing legacy endpoint is equivalent to the current API.

### 4.3 Structured anime data sources

- AniList GraphQL: primary structured anime metadata lookup.
- Jikan API: secondary metadata source / fallback.
- Official anime, publisher, studio and streaming-service sources: preferred evidence for announcements, release dates and availability.
- Reputable anime reporting: secondary evidence, clearly labelled as reporting rather than official confirmation.

AniList and Jikan are data APIs, not search API keys. Public endpoints still require rate-limit handling, caching, source attribution where applicable, and schema validation.

## 5. API key inventory and user action

The code defines seven secret slots for the currently implemented AI/search integrations:

1. `GEMINI_API_KEY`
2. `GROQ_API_KEY`
3. `NVIDIA_API_KEY`
4. `OPENROUTER_API_KEY`
5. `DECODO_API_KEY`
6. `LANGSEARCH_API_KEY`
7. `TAVILY_API_KEY`

The repository's `.env.example` documents these names. The Render service metadata endpoint does not expose the environment-variable inventory, so the presence of these names in code does **not** prove that their values are configured in Render. Never print or transmit secret values in logs, chat, reports or source control.

**Operator action:** In Render → ani-zeo-foundation → Environment, add or confirm the seven keys above only where missing. Keep values private. Do not create duplicate keys to multiply quotas or bypass provider limits. Do not add a Bytez key yet; it is pending evaluation. No additional search API key is requested at this stage.

After the operator confirms the keys are saved, validate configuration safely through provider health checks that return only configured/missing/valid/invalid/rate-limited status and never return key values.

## 6. Runtime request pipeline

1. Receive Telegram update and validate webhook secret.
2. Enforce idempotency so Telegram retries do not duplicate work.
3. Load user preferences, recent conversation context and permitted memory.
4. Detect intent, anime entities, language, follow-up context and conservative typos.
5. Route deterministic metadata/command requests directly to structured data sources where possible.
6. For freshness-sensitive questions, invoke live research; never silently substitute model memory for unavailable current evidence.
7. Search through configured providers in order with bounded timeouts, retries and cooldowns.
8. Normalize and deduplicate results; reject malformed, irrelevant or unsafe URLs.
9. Rank evidence by source provenance, relevance, publication time and corroboration.
10. Draft the response through the configured AI provider router using shared mandatory presentation rules.
11. Verify factual claims, dates, identifiers and source support; qualify or withhold unsupported claims.
12. Apply deterministic Telegram-safe formatting and language preferences.
13. Persist only necessary conversation and usage data; do not store raw prompts/responses in usage telemetry.
14. Return one polished Telegram response with compact source links when appropriate.

## 7. AI provider router requirements

- Provider-neutral interface; no business logic may depend on a vendor-specific SDK or response format.
- Configurable priority order and per-provider model identifiers.
- Bounded per-attempt and whole-request timeouts.
- Retry only transient failures; do not retry invalid credentials or unsupported model errors indefinitely.
- Classify authentication, permission, quota, rate-limit, timeout, server, malformed-response and truncation failures separately.
- Validate response content and finish reason; reject empty or truncated answers when completeness is required.
- Track provider/model, operation, latency, finish reason and provider-reported token usage where available.
- Do not invent token usage or cost when provider data is missing.
- Keep Gemini-only operation possible: the application must run with Gemini as the sole enabled AI provider, with graceful failure when Gemini is unavailable.
- Keep the development workflow vendor-neutral; source code, tests, deployment and configuration must not require ChatGPT/OpenAI.

## 8. Search, evidence and anti-hallucination requirements

- Search is required for freshness-sensitive questions.
- Search-provider availability and evidence quality are separate signals.
- Prefer official primary sources; distinguish official confirmation, reputable reporting and unverified sources.
- Store source URL, title, domain, publication date when known, retrieval time, provider and verification status.
- Deduplicate mirrored stories and identify conflicting dates/claims.
- Never treat a search snippet alone as official confirmation.
- If evidence is unavailable or conflicting, say so rather than inventing an answer.
- Cache by normalized query and freshness class with explicit TTLs; historical questions must not be incorrectly filtered as recent-only.
- Keep a research archive with provenance and last-checked timestamps.

## 9. Search-provider evaluation and expansion policy

Evaluate Decodo, LangSearch and Tavily using the same anime-focused test set:
- current announcements and release dates;
- official studio/publisher confirmations;
- regional streaming availability;
- historical announcements;
- Telugu/India-specific queries;
- typo-heavy and Roman Telugu queries;
- irrelevant-result and false-premise cases.

Measure successful usable-evidence rate, primary-source hit rate, latency, errors, quota consumption and cost/free-tier constraints. Keep the existing three until measurements justify changing their order. Only propose another search API if it materially improves coverage or resilience and its free-tier/terms meet the project's requirements.

## 10. Memory, privacy and user controls

- Separate short-term conversation context from explicit preferences and durable long-term memory.
- Persist only useful, purpose-limited information.
- Provide understandable privacy, settings and deletion controls.
- Prevent cross-user context leakage with user-scoped database queries and tests.
- Never log API keys, bot tokens, webhook secrets or database credentials.
- Usage telemetry must not contain message content.

## 11. Quota, performance and scale

- Cache structured anime lookups and research results with appropriate TTLs.
- Deduplicate identical in-flight searches.
- Enforce per-user burst/daily limits and provider concurrency controls.
- Apply provider cooldowns and bounded queues under load.
- Avoid unnecessary LLM calls for deterministic requests.
- Monitor latency, error rates, provider availability, request counts, token usage and database health.
- Treat 2,000–5,000 users as a capacity-planning target, not a guarantee. Load-test before making capacity claims.
- Upgrade hosting or paid quotas only when measured demand requires it and the operator approves.

## 12. Testing and release gates

Required tests include:
- provider configuration, missing/invalid keys and model errors;
- fallback order, timeouts, rate limits, retries and cooldowns;
- empty, malformed and truncated AI responses;
- search normalization, deduplication, relevance and provider fallback;
- evidence provenance, conflicting claims, dates and unsupported assertions;
- English, Tenglish, Roman Telugu, Telugu script, typos and follow-up context;
- mandatory formatting across all AI providers;
- webhook idempotency and Telegram retry behaviour;
- user privacy, deletion and cross-user isolation;
- quota controls, caching and concurrent requests.

Release gates:
- CI tests pass.
- No secrets in source, logs or artifacts.
- Live claims are evidence-backed or explicitly qualified.
- Provider failures are observable and recoverable.
- No cross-user data leakage.
- Existing database data and migrations are preserved.
- Staging/controlled verification succeeds before production deployment.
- Production deployment requires separate explicit approval; Render auto-deploy stays disabled until approved.

## 13. Phased implementation plan

### Phase 0 — Audit and configuration verification
Inspect the full deployed branch, old bot repository, Render configuration, database schema/migrations, provider adapters, search adapters, CI and recent logs. Verify configured credentials without exposing values.

### Phase 1 — Stable foundation
Resolve reliability defects in routing, timeouts, response validation, formatting, observability and webhook processing. Preserve valuable existing features and data.

### Phase 2 — Evidence-first anime research
Harden AniList/Jikan lookups, live search, source ranking, provenance, conflict handling, caching and historical research.

### Phase 3 — Human conversation and personalization
Improve intent/follow-up/language handling, preference controls, memory selection and privacy guarantees.

### Phase 4 — Provider and quota engine
Standardize provider adapters, health states, usage accounting, fallback policy, Gemini-only mode and provider-neutral configuration. Evaluate Bytez before any implementation.

### Phase 5 — Telegram UX and capacity
Improve onboarding, typing feedback, single-response delivery, queueing, concurrency and load tests.

### Phase 6 — Feature restoration and final verification
Compare against the original bot repository, restore valuable missing features safely, run regression and integration suites, then prepare a release candidate.

### Phase 7 — Deployment review
Present exact changes, test evidence, remaining risks and migration plan. Deploy only after explicit operator approval.

## 14. Current known limitations

- Render service details confirm the connected repository, deployed branch, free plan, Singapore region and auto-deploy disabled; they do not reveal environment-variable names or secret values.
- Presence of a key name in source/configuration is not proof of a configured or working credential.
- Existing adapters and tests need a full code-path audit and live credential verification.
- Bytez is not implemented.
- The three current search integrations have not yet been benchmarked against a shared test set.
- This document is the architecture baseline, not a claim that all roadmap work is complete.
