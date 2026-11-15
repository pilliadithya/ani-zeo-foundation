# Ani Zeo — Project Vision

**Product:** Ani Zeo  
**Positioning:** Your anime friend. Not just an AI bot.  
**Primary experience:** Telegram-first anime intelligence and discovery companion.  
**Snapshot date:** 2026-11-15

## Mission

Build a reliable, personalised, multilingual Anime Intelligence Companion that helps people discover anime and manga, understand stories and characters, stay up to date, remember their viewing journey, and receive trustworthy answers.

Ani Zeo must not behave like a generic chatbot that confidently invents anime facts. The product should prefer grounded knowledge, disclose uncertainty, and explain when information cannot be verified.

## Six product pillars

1. **Discover** — anime and manga discovery, recommendations, beginner-friendly picks and hidden gems.
2. **Understand** — characters, stories, powers, watch order, explanations and context.
3. **Stay updated** — airing schedules, anime news, announcements and release information.
4. **Remember** — watchlists, progress, preferences and consent-based personalisation.
5. **Converse** — natural multilingual conversation with a consistent, friendly anime-companion personality.
6. **Verify** — source-backed answers, evidence attribution, uncertainty handling and anti-hallucination safeguards.

## Product principles

### Accuracy before fluency
- Structured sources and verified retrieval take priority over model memory.
- Do not invent titles, characters, dates, episode numbers, studios, platforms, chapters or announcements.
- If reliable evidence is unavailable, say so plainly and offer a useful next step.
- Separate confirmed facts, reported claims, inference and unknown information.

### Language belongs to the user
- Respect the user's selected language and script across every AI provider and feature.
- Supported language modes include English, Tenglish, Hinglish and Tanglish.
- Do not silently switch to English when the user has selected another language.
- Keep terminology and formatting natural for the selected language.

### Companion, not just chatbot
- Maintain friendly, passionate, concise and context-aware conversation.
- Use conversation history and user preferences only within consent and privacy boundaries.
- Respect spoiler preferences and viewing progress.

### Free-first, reliable engineering
- Prefer sustainable free or low-cost infrastructure, caching and structured APIs.
- Never promise a user capacity or quota that has not been measured.
- Instrument latency, provider failures, token usage and cost.
- Degrade safely when a provider or source is unavailable.

## Knowledge strategy

Use a layered knowledge model:

- **Structured knowledge:** canonical anime/manga metadata and relationships from dependable APIs such as AniList and Jikan.
- **Live knowledge:** current news, schedules and announcements retrieved from relevant sources.
- **Historical knowledge:** retained evidence with source, retrieval time and freshness.
- **Conversation knowledge:** user context, preferences and prior turns, governed by consent and retention rules.

Potential source families include AniList, Jikan, official anime websites, Anime News Network and Crunchyroll News. Source selection must be relevance- and claim-specific; a source list is not a guarantee that any particular fact is verified.

## Trust and safety requirements

- Claim-level evidence attribution should be the target for factual research answers.
- Detect conflicting, stale, duplicate and unsupported claims.
- Distinguish source text matching from semantic entailment; lexical overlap alone is not proof.
- Treat web pages and retrieved content as untrusted input, never as instructions.
- Protect user data, credentials and provider secrets.
- Use consent-based memory and clear spoiler controls.

## Non-goals

- Replacing structured anime databases with model-generated guesses.
- Restoring a legacy monolithic bot wholesale.
- Claiming production scale, accuracy, availability or multilingual quality without measured tests.
- Migrating infrastructure merely for novelty; measure first.

## Success measures to establish

The project should define and measure:
- factual accuracy and unsupported-claim rate;
- retrieval relevance and source coverage;
- correct intent/entity routing;
- language and script adherence;
- response latency and timeout rate;
- provider availability and quota exhaustion;
- cost per successful request;
- webhook delivery and duplicate-update handling;
- memory consent and spoiler-protection correctness;
- load behaviour under realistic concurrent usage.

Any proposed target (including thousands of users or a large benchmark set) remains **Planned** until a reproducible test demonstrates it.
