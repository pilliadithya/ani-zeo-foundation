# Ani Zeo — Complete Companion Implementation Programme

**Created:** 2026-11-15  
**Base:** `rebuild/master-architecture-v1`  
**Programme branch:** `feat/ani-zeo-complete-companion-roadmap`  
**Policy:** Free-first; feature branches and PRs; production deploy only after user approval.

## Objective

Implement the simulated Ani Zeo experience as a real Telegram product: anime discovery, understanding, current research, personalised recommendations, watchlist/progress, consent-based memory, multilingual conversation, spoiler protection, evidence-backed answers, and rich media.

The simulation is a product target, not a claim that these features already exist.

## Delivery rules

Every milestone must:
1. Start with an inspection of current production-branch code and database schema.
2. Have an explicit scope and acceptance criteria.
3. Be implemented on an isolated feature branch.
4. Include automated tests for success, failure, boundary and privacy cases.
5. Be reviewed for security, data migration and free-tier impact.
6. Be delivered in a PR with test results and known limitations.
7. Be deployed only after explicit user approval.
8. Be tested by the user in Telegram before the next milestone is treated as accepted.

Do not request API secret values in chat. If a new key is essential, tell the user which provider, why it is needed, and ask them to add it directly in Render's environment settings. Prefer existing configured services and no-key sources first.

## Programme phases

### M0 — Reliability and delivery foundation
**Goal:** Ensure requests are processed predictably and provider failures do not break the conversation.

Scope:
- Re-audit webhook, update idempotency, per-user locking, request deadlines and error handling.
- Replace the fixed 2.7-second sequential search-provider cap with a tested total deadline and provider-specific budgets.
- Preserve bounded retrieval, relevance filtering, safe cancellation and fail-closed behaviour for current/historical facts.
- Add structured provider outcomes (success, timeout, rate-limited, auth/configuration, empty/relevance miss, malformed response).
- Respect Retry-After where supported; use bounded cooldown/backoff and avoid retry storms.
- Ensure selected language is passed through all research and AI paths.
- Add regression tests for provider latency combinations, all providers unavailable, cancellation, 429 and malformed payloads.

Acceptance:
- Fast provider can return useful evidence even when another provider stalls.
- Slow providers cannot exceed the overall request budget.
- A 429 or timeout is not reported as an invalid credential.
- No unsupported live fact is generated when evidence is absent.
- Existing webhook and idempotency tests remain green.

### M1 — Structured anime and manga intelligence
**Goal:** Make the six pillars usable through real data.

Scope:
- Search anime and manga via AniList/Jikan.
- Resolve titles, aliases, romanised/native names and ambiguous matches.
- Anime details: synopsis, genres, format, status, episode count, season/year, score and cover.
- Character profiles and character-to-anime relationships, using supported source coverage.
- Studio profiles and works where source data supports it.
- Watch/read order with franchise-specific validation and clear canon/filler distinctions.
- Airing schedule and episode metadata.
- Recommendations using genre, format, score, themes and explicit user preferences.
- Pagination and disambiguation in Telegram.

Acceptance:
- Every entity result is tied to a stable source ID and source URL.
- Ambiguous titles ask the user to choose instead of guessing.
- Missing source fields are omitted, not invented.
- Recommendations explain why each title was selected.
- Tests cover no result, multiple matches, aliases, manga/anime distinction and API outage.

### M2 — Research, evidence and anti-hallucination
**Goal:** Ground current and historical claims in traceable evidence.

Scope:
- Shared retrieval interface for configured search providers.
- Source normalization, canonical URL deduplication, freshness and publisher independence.
- Claim extraction and claim-to-evidence association.
- Semantic entailment/contradiction checks with conservative fallback; lexical overlap alone is not proof.
- Official confirmation versus reporting, rumour and speculation labels.
- Source citations and dates in Telegram output.
- Evidence archive with expiry/freshness policy and provenance.
- SSRF/redirect/DNS/size/timeout controls for page fetching.

Acceptance:
- Each material factual claim has supporting evidence or is clearly labelled unverified.
- Conflicting sources are shown as conflicts.
- Duplicate syndications are not presented as independent corroboration.
- Historical archive is not mistaken for current status.
- Retrieval failure produces an honest fallback.

### M3 — Conversation intelligence and personality
**Goal:** Make conversations coherent, helpful and multilingual.

Scope:
- Intent taxonomy for greetings, anime questions, character, studio, recommendation, watch/read order, live news, schedule, industry questions and follow-ups.
- Entity resolution and context references ("he", "that anime", "what about season 2?").
- Conservative typo correction and romanised Telugu/Tanglish understanding.
- Language and script enforcement for English, Tenglish, Hinglish, Tanglish and Telugu script.
- Shared provider-neutral system principles and response contract.
- Adaptive formatting by intent and answer length.
- Friendly personality without allowing style to override factuality.
- Safe topic boundary and off-topic handling.

Acceptance:
- The selected language/script is respected in replies, including fallback/error responses.
- Follow-ups resolve against recent context without stale-topic capture.
- All providers follow the same safety, evidence and formatting rules.
- No false certainty introduced by formatting or personality.

### M4 — Personal anime companion
**Goal:** Persist a user's anime journey safely.

Scope:
- Database-backed watchlist, favourites and plan-to-watch/watching/completed/dropped statuses.
- Episode/chapter progress with spoiler boundary.
- Personal recommendations using explicit preferences.
- Memory categories with user consent, confidence and edit/delete controls.
- Privacy commands, data export/deletion behaviour and retention policy.
- Conversation summary only where useful and consented.
- No sensitive inferred profile attributes.

Acceptance:
- Watchlist/progress survives restarts and multiple sessions.
- User can inspect and delete saved data.
- Spoiler-sensitive answers never reveal beyond saved progress.
- Memory can be disabled independently of basic bot operation.
- All user data is scoped to the authenticated Telegram user ID.

### M5 — Rich Telegram experience and images
**Goal:** Make the bot visually useful without sacrificing speed or reliability.

Scope:
- Anime cover images from AniList/Jikan.
- Character artwork where available from legitimate metadata/image sources.
- Studio artwork only where a reliable image is available.
- Telegram photo + concise caption cards, with text fallback.
- Inline keyboards for pagination, title disambiguation, watchlist actions and progress updates.
- Image URL validation, bounded requests and caching of metadata/URLs.
- Avoid copying copyrighted artwork into project storage unless the source/licence permits it.

Acceptance:
- Correct image is associated with the correct entity.
- Broken or missing images fall back to readable text.
- Captions fit Telegram limits and are safely escaped.
- Images do not block the entire response on slow networks.
- Buttons are authenticated to the requesting user and idempotent.

### M6 — Provider, quota and free-tier management
**Goal:** Keep the service economical and robust under real usage.

Scope:
- Provider health/circuit breaker state and Retry-After handling.
- Per-provider request budgets and concurrency limits.
- Per-user and global quotas with clear user-facing limits.
- Cache structured metadata and research results with freshness-aware keys.
- Token/cost telemetry using provider-reported usage where available.
- Queue/backpressure only if measurements justify it.
- Document free-tier constraints and safe degraded modes.

Acceptance:
- Provider outage does not cause retry storms.
- Quotas are enforced consistently and transparently.
- Caching does not serve stale current-news answers as current.
- Cost reporting distinguishes actual provider usage from estimates.
- Capacity claims are supported by load tests, not guesses.

### M7 — Evaluation, security and release
**Goal:** Verify the end-to-end product against the conversation simulation.

Scope:
- Build a versioned test set covering the 20-message simulation and expanded adversarial cases.
- English, Tenglish, Hinglish, Tanglish and Telugu-script test suites.
- Spoiler leakage, wrong-entity, wrong-date, hallucinated-announcement and source-conflict tests.
- Telegram integration tests and manual user acceptance.
- Security review: webhook, database/RLS, outbound URL fetching, secrets, privacy and callback authorization.
- Load tests at realistic free-tier limits; no unsupported scale promises.
- Deployment checklist, rollback plan and operational runbook.

Acceptance:
- Each simulated interaction maps to a test case and expected behaviour.
- Critical accuracy, privacy and spoiler tests pass.
- Production smoke tests pass after user-approved deployment.
- Known limitations and rollback steps are documented.

## First implementation task

Start M0 by confirming the current production branch code and existing tests. The current production source inspected for this plan shows `AnimeResearchService.search_fallback_answer` uses an 8-second overall deadline but gives each sequential provider at most 2.7 seconds, while the Decodo and LangSearch clients are configured with 12- and 18-second HTTP timeouts. This can cancel a provider before its own timeout. Verify this against the branch HEAD before changing it.

Also verify all constructor arguments, provider order and current tests before assuming any provider is configured or available.

## Free-first sourcing strategy

- Prefer existing AniList GraphQL and Jikan public endpoints for structured metadata, subject to their current rate limits and terms.
- Reuse existing Gemini/Groq and search-provider configuration only when present and healthy.
- Prefer free/open-source Python libraries already compatible with Python 3.11.
- Cache source metadata and image URLs; do not build an expensive image proxy by default.
- No paid model, paid search provider, paid hosting upgrade or new subscription without user approval.
- Free tiers are not unlimited and may have rate limits, cold starts or policy changes.

## User-provided items that may be needed later

No new secrets are required to begin M0. If a later milestone needs a missing provider, ask for the provider name and explain the purpose; user should add the secret directly in Render, never paste it into chat.

For feature decisions, ask only when necessary:
- Preferred language defaults and whether users can change per message.
- Spoiler default (recommend spoiler-free by default).
- Image fallback preference (text-only if image unavailable).
- Whether to preserve current Telegram bot identity and command names.

Do not block the initial reliability work on these preferences; use safe defaults and expose settings later.

## Progress log

| Date | Milestone | Status | Evidence |
|---|---|---|---|
| 2026-11-15 | Programme plan | Drafted | This document |
| 2026-11-15 | M0 reliability audit | In progress | Production-branch source inspection; confirm HEAD and test suite next |
