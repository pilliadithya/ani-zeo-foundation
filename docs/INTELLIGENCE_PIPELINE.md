# Ani Zeo Intelligence Pipeline — Research & Implementation Plan

Status: design decision for the isolated `fix/ai-reliability-and-webhook-dedup` branch.
Scope: one message pipeline; do not introduce a second chatbot or duplicate orchestration path.

## Executive decision

Reuse the strongest parts of the original `ani-zeo-bot` architecture, but simplify and harden them for the Foundation:

- Keep one Telegram entry point and one orchestration path.
- Keep intent detection cheap and deterministic; do not spend an LLM call just to classify every message.
- Use structured anime APIs for structured anime facts.
- Use web search only for freshness, external coverage, or facts not available in the anime database.
- Normalize every source into one evidence/context contract.
- Make one final response-generation call, except when Gemini native Google Search grounding is selected (that call already searches and synthesizes).
- Preserve provenance and source URLs so answers can cite evidence.
- Cache data retrieval, not personalized natural-language answers by default.
- Keep search failures non-fatal; conversation must still work.

## What the original Ani Zeo already designed

The original public repository, `pilliadithya/ani-zeo-bot`, already contains a much more mature knowledge architecture than the current Foundation:

- `ai/message_handler.py`: conversation entry point, short-lived per-user history, intent detection, context construction, and final AI response.
- `services/intent.py`: lightweight intent classifier.
- `services/knowledge_router.py`: priority-based source routing; internal anime sources first, live sources only when needed, web search as primary or supplement depending on intent.
- `services/anime_search.py`: AniList GraphQL primary + Jikan REST fallback, normalized into an `AnimeSearchResult`, with positive and negative caching.
- `services/anime_intelligence.py`: aliases, franchise resolution, watch orders and manga continuation guidance.
- `services/anime_news.py`: RSS/news and trending aggregation.
- `services/web_search.py` and `services/brave_search.py`: provider abstraction, timeout, cache, normalized results.
- `services/context_builder.py`: a single gate that converts raw API responses into clean, source-agnostic context; raw API JSON is not sent to the model.
- `ai/router.py`: provider fallback plus provider health cooldowns.
- `ai/formatter.py`: Telegram-safe formatting and message splitting.

Original architecture documentation: https://github.com/pilliadithya/ani-zeo-bot/blob/main/ARCHITECTURE.md

The old project is a design reference, not a code dependency. Do not copy its old in-memory/JSON persistence model into Foundation; Foundation already has PostgreSQL-backed profiles, messages and memory.

## What should be reused, changed, and avoided

### Reuse
1. Intent → knowledge routing → context builder → AI router → formatter.
2. AniList-first/Jikan-second anime lookup.
3. Source-neutral dataclasses rather than raw API JSON.
4. Provider registry interfaces, timeout handling and caching.
5. Search as supplemental evidence for anime news/trending and primary evidence for genuine open-web questions.
6. Provider health/cooldown concepts from the old AI router.

### Improve
1. The old knowledge router can call sources sequentially. In Foundation, run independent lookups concurrently only when both are actually useful, under one strict total deadline.
2. Use typed intent and retrieval plans: `CHAT`, `ANIME_LOOKUP`, `ANIME_NEWS`, `AIRING`, `WATCH_ORDER`, `RECOMMENDATION`, `LIVE_WEB_RESEARCH`, `GENERAL_KNOWLEDGE`.
3. Resolve a title once, then reuse its canonical AniList ID for related lookups; do not repeatedly fuzzy-search the same title.
4. Add query/result cache keys that include source, normalized query, locale, and relevant filters. Use shorter TTLs for airing/news and longer TTLs for stable metadata.
5. Deduplicate results by canonical URL and normalized title; rank by relevance, recency and source quality.
6. Treat retrieved page text as untrusted data. Never follow instructions embedded in pages or let search results alter system policy.
7. Track per-stage latency and source status without logging user secrets or full private messages.
8. Add explicit total latency and evidence/token budgets; one slow optional source must not hold the reply indefinitely.

### Avoid
- Searching the web for ordinary greetings, emotional chat, simple opinions, or stable anime metadata already available in AniList.
- Calling multiple LLMs for intent classification, query rewriting, summarization and final answer on every message.
- Running all search engines for every query.
- Making DuckDuckGo Instant Answer API a full-web-search fallback. It is a zero-click/instant-answer API, not a complete web results API.
- Caching user-specific final answers across users.
- Returning unsupported claims when all sources fail.

## Single production message pipeline

```text
Telegram update
  -> authenticate + durable update_id deduplication
  -> load profile + recent conversation + memory
  -> cheap intent / entity extraction
  -> build one RetrievalPlan
       CHAT                 -> no retrieval
       ANIME_LOOKUP         -> AniList; Jikan only if no confident match / outage
       WATCH_ORDER          -> canonical franchise intelligence + AniList relations
       AIRING / NEWS        -> AniList schedule / RSS; web supplement for latest reporting
       RECOMMENDATION       -> AniList recommendation/genre/tag data + user preferences
       LIVE_WEB_RESEARCH   -> search provider strategy
  -> execute only required independent retrievals concurrently (strict deadline)
  -> normalize, validate, deduplicate and rank evidence
  -> build compact ContextEnvelope with provenance and freshness
  -> one AI synthesis call through Gemini -> Groq -> NVIDIA -> OpenRouter
       OR Gemini native Google Search grounding as a single integrated search+synthesis call
  -> Telegram formatter + citations/source links
  -> persist user/assistant messages and update memory asynchronously/best-effort
```

This is one pipeline with optional retrieval branches, not a second pipeline.

## Retrieval strategy

### Anime data
- Primary: AniList GraphQL for anime/manga metadata, relations, characters, staff, studios and airing schedules.
- Secondary: Jikan REST (MyAnimeList-derived) when AniList is unavailable or a title match is uncertain.
- Do not merge conflicting fields blindly. Keep per-field provenance and prefer the source most appropriate for that field.
- Use AniList IDs as canonical internal entity IDs after a title is resolved.
- Respect AniList rate-limit headers and `Retry-After`; current official documentation describes a normal 90 requests/minute limit and notes temporary degraded limits may apply.

### Live web research
- Tavily: preferred first integration for AI-oriented basic search; use advanced search only for explicit deep research.
- Brave: strong alternative/secondary provider. Its current official pricing page advertises $5 free monthly credits, then $5/1,000 Search requests. Do not assume unlimited free use; configure a hard spend cap and usage monitoring.
- Google Search grounding: best used as Gemini's integrated search-and-synthesis path when the configured Gemini model/account supports it. It is not just another raw result provider: native grounding returns a synthesized answer plus citation annotations. Avoid paying for an extra final LLM call in this path.
- DuckDuckGo Instant Answer: optional enrichment only; not a general web-search provider.

Fallback order should be configuration-driven and health-aware. A failure or quota limit moves to the next configured source immediately; do not retry quota errors. Use circuit-breaker cooldowns for repeated failures.

## Latency targets and budgets

Initial targets (measure and tune; these are engineering goals, not guarantees):
- Normal conversation, warm instance: 2–6 seconds.
- Cached anime lookup + response: 2–6 seconds.
- Live research: aim for 5–12 seconds total.
- Hard total generation/retrieval deadline: 18 seconds for ordinary user messages.
- Search stage budget: 4 seconds per provider attempt; one fallback at most inside the shared search deadline.
- Optional image/cover lookup must not block the text reply; fetch it only when the user asks for a title/details or when it can be attached after the text response.
- Send Telegram typing action while working; no media GIF placeholder. Stop typing as soon as the reply is ready.

Render free-instance cold starts are a separate infrastructure delay and must be measured separately from provider/search latency.

## Evidence contract

Every retrieval adapter should return normalized records with:
- `kind` (anime, manga, news, web page, airing event, character, staff, studio)
- `title`
- `summary` / selected factual fields
- `canonical_url`
- `source_name`
- `retrieved_at`
- `published_at` when known
- `confidence` or match confidence
- `freshness_class` (stable, recent, live)
- `entity_id` where available

Context builder should cap the number of sources and total context characters/tokens. Prefer direct official/licensor/studio sources for release dates and streaming rights, official AniList data for database facts, and reputable reporting for news. If sources conflict, disclose the conflict instead of blending them.

## Caching

- AniList/Jikan stable metadata: 6–24 hours.
- Character/staff/studio relations: 12–24 hours.
- Airing schedule: 5–15 minutes.
- News: 5–15 minutes.
- General web search: 15–30 minutes.
- Negative anime title lookups: 5–10 minutes.
- Cache retrieval records in PostgreSQL/Redis-compatible abstraction later; in-process TTL is acceptable for the first single-instance milestone but is not shared across instances.
- Never share personalized answer cache entries between users.

## Implementation sequence on this feature branch

1. Add this architecture decision record (this file).
2. Build a single normalized retrieval contract and search-provider interface.
3. Integrate Tavily and Brave with tests, quotas, timeouts, cache and circuit breaker.
4. Add AniList/Jikan normalized anime adapter and canonical entity reuse.
5. Connect intent → retrieval plan → context builder in the existing Foundation message path.
6. Add citation formatting and safe source-link output for Telegram.
7. Add offline tests for intent routing, provider failures, cache expiry, result deduplication, prompt-injection resistance and latency budgets.
8. Add opt-in live smoke tests; never make CI depend on external provider availability.
9. Test against the feature branch's Render service before merging to main.

Do not merge until all unit/integration tests pass and manual Telegram tests verify casual chat, anime lookup, latest news, search failure fallback, citations, and no duplicate replies.

## External references

- AniList GraphQL getting started: https://docs.anilist.co/guide/graphql/
- AniList media queries and title search: https://docs.anilist.co/guide/graphql/queries/media
- AniList rate limits: https://docs.anilist.co/guide/rate-limiting
- Jikan API: https://jikan.moe/
- Tavily Search API: https://help.tavily.com/articles/4840311948-tavily-search-api
- Tavily basic vs advanced: https://help.tavily.com/articles/6938147944-basic-vs-advanced-search-what-s-the-difference
- Brave Search API pricing: https://api-dashboard.search.brave.com/documentation/pricing
- Brave LLM Context / agent search: https://api-dashboard.search.brave.com/app/documentation/web-search
- Gemini Google Search grounding: https://ai.google.dev/gemini-api/docs/google-search
- DuckDuckGo Instant Answer limitations: https://www.postman.com/api-evangelist/duckduckgo/documentation/i9r819s/duckduckgo-instant-answer-api
