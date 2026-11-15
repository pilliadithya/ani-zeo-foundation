# Ani Zeo — Intent Intelligence & Conversation Continuity Upgrade

**Date:** 2026-11-15  
**Base:** `rebuild/master-architecture-v1`  
**Branch:** `feat/conversation-intelligence-and-continuity-v1`

## Product decisions (user-confirmed)
- Spoilers are only provided when the user asks for spoilers. Default responses must avoid revealing important plot developments.
- The saved language preference is authoritative on every turn. Do not silently switch to message-language detection or a model's default language.
- Include relevant images whenever reliable, relevant artwork is available. A missing/broken image must never block the text answer.
- Do not interrupt ordinary questions with repeated consent/acceptance prompts. Consent controls persistence, memory and personalization; non-consented users should receive stateless processing where technically safe. The explicit onboarding flow remains available for users who want stored history and personalization.

## Audit findings from current production branch

### Intent detection
The current `AnimeResearchService.detect_intent` is a deterministic regex/rule classifier. It uses a manually maintained anime entity list and vocabulary, recognizes a limited set of English, Romanized Telugu and Telugu-script references, uses a maximum of 10 recent messages and at most 6 context items, returns `unclear` at confidence 0.55 when patterns do not match, and maps both `off_topic` and `unclear` to `scope=redirect`.

That last rule is a significant false-negative source: unfamiliar titles, characters, natural-language paraphrases, code-switching and short contextual turns can be redirected even when the user intended an anime question. Expanding regex lists alone will not scale.

### Conversation continuity
There are existing foundations: recent message history, a summary memory, `conversation_state.active_topic`, and resolved-entity JSON. However, topic extraction after a response depends on `extract_title` and a fixed `INTENT_ENTITIES` list; unknown/new entities therefore often fail to become the canonical active topic. Follow-up resolution is inferred again from regexes rather than a dedicated entity/reference-resolution step. The AI prompt receives truncated recent history plus a short memory summary, but not a versioned, structured conversation state with explicit unresolved references, user corrections, task state and last answer subject.

### Consent gate
The current message handler returns a `/start` onboarding instruction for every message from a profile without `consented_at`. This blocks stateless questions. Intended behaviour: consent controls saving messages, memory and personalization, without forcing a consent prompt as the answer to an ordinary question. Implementation must not store non-consented message content or create conversation memory.

### Language and spoilers
The system prompt says saved language is authoritative, but the follow-up translation branch can override it when a message says “in Telugu” or another language. This conflicts with the latest user decision. Remove implicit per-turn overrides; only a dedicated explicit language-setting action should change saved preference. Spoiler guidance is inconsistent (“warn before major spoilers when progress is unknown”); default to spoiler avoidance and only disclose after an explicit request.

### Images
An AniList cover lookup and Telegram photo send already exist for one title-metadata path. This is not a general image enrichment pipeline. Extend it to relevant anime/character/manga cards with entity-ID matching, source URL validation, optional sending and a text fallback. Never guess that an image depicts the requested entity.

## Target architecture

### 1. Input normalisation (non-destructive)
- Preserve original user message exactly for transcript and audit.
- Create a separate normalized copy for typo correction, whitespace and language/script hints.
- Never rewrite uncertain names based on a weak fuzzy match.
- Keep original text and corrected text available downstream.

### 2. Hybrid intent understanding
**Fast deterministic layer**
- Recognize high-confidence commands, greetings, known structured intents and obvious off-topic requests.
- Produce intent, scope, confidence, entities, references, normalized text, and decision evidence.
- Unknown does not equal off-topic.

**AI intent resolver**
- Invoke configured AI provider chain only for low-confidence/ambiguous cases.
- Request strict JSON with allowlisted intent schema, confidence, domain, entity candidates, resolved references, task type and concise normalized query.
- Supply relevant recent context and structured state; treat user messages as untrusted data.
- Validate JSON schema and confidence bounds; reject malformed/unsupported labels.
- Never let classifier invent entity facts, dates or source evidence.
- If classifier providers fail, ask a brief clarification when appropriate instead of falsely redirecting an anime request.
- Keep a hard timeout and token budget so classification cannot stall Telegram.

**Routing precedence**
1. Explicit user correction or clear current request.
2. Explicit language setting / privacy command.
3. High-confidence current intent.
4. AI-assisted ambiguous intent and entity resolution.
5. Clarification for unresolved ambiguity.
6. Off-topic redirect only when confidently outside anime/manga scope.

### 3. Conversation continuity engine
Build a provider-neutral context snapshot before answer generation:
- current user request and original wording;
- selected language;
- last relevant user/assistant turns;
- canonical active topic and entity IDs;
- entity aliases and resolved pronouns/references;
- recent corrections and explicit user constraints;
- active task (watch-order explanation, research, comparison, etc.);
- consented long-term memory summary;
- spoiler preference/progress when available.

Use a token-aware relevance selector, not simply the last N messages. Keep current request intact, include turns needed to resolve references, and summarize older turns with a cursor. Never let old topics override an explicit new subject. User corrections update canonical state.

### 4. Model provider continuity
Every answer provider (Gemini, Groq, NVIDIA, OpenRouter when configured) receives the same immutable context snapshot and shared system rules. Provider failover must not reset conversation state, language, requested depth, evidence or output format. A provider switch is invisible to the conversation. The AI provider is not the source of truth for stored state.

### 5. Response and safety audit
- Saved language remains authoritative on all ordinary turns.
- Spoiler-free by default; explicit spoiler request required to reveal major plot developments.
- Current facts still require retrieved evidence and claim verification.
- Distinguish intent confidence from factual confidence.
- Never use model intent classification as factual evidence.
- Use structured output formatting only when useful; do not force a template on casual replies.

## Implementation sequence

### CI-1 — Instrumented intent audit and false-negative fixes
- Add a versioned intent evaluation corpus from reported failures and synthetic paraphrases.
- Include English, Tenglish, Hinglish, Tanglish and Telugu script.
- Test unseen titles/characters, aliases, misspellings, mixed-language messages, vague follow-ups, topic switches, multi-intent requests, corrections and greetings.
- Record classifier outcome/confidence/route reason without storing secrets or logging full private messages.
- Separate `unclear` from `off_topic`; do not redirect solely because rule classifier did not recognise a phrase.

### CI-2 — Model-assisted intent and entity resolver
- Add a bounded classifier call using existing configured AI providers.
- Strict JSON schema, allowlisted intents, validation and deterministic fallback.
- Invoke only on uncertain turns to preserve free-tier quota and latency.
- Do not require a new API key if an existing configured provider is available.

### CI-3 — Canonical continuity snapshot
- Resolve active topic and entities from model output plus structured sources.
- Update `conversation_state` only after successful delivery.
- Preserve context across provider failover.
- Improve history selection and summary cursor handling.
- Add explicit topic-switch and correction tests.

### CI-4 — Consent-safe stateless mode
- For users who have not consented, answer without writing transcript, summaries, preferences or memory.
- Keep `/start` as explicit consent/onboarding entry point.
- Never persist unconsented user content. Verify every write path, including usage telemetry and research archive associations, before enabling this mode.

### CI-5 — Language, spoiler and image consistency
- Enforce saved language at router boundary and in every fallback.
- Remove implicit language changes from follow-up handling.
- Default spoiler avoidance; disclose only on explicit request.
- Add entity-matched images to relevant response types with graceful text fallback.

### CI-6 — Regression, shadow and acceptance testing
- Run deterministic corpus tests and model-resolver fixture tests.
- Shadow-classify only if privacy-safe and quota allows; do not silently store user prompts for analytics.
- Compare old/new intent accuracy by category and language.
- Test long conversations, corrections, topic switches, provider failover and Telegram response delivery.
- User acceptance test in Telegram before production rollout.

## Initial implementation priority
Begin with CI-1 and CI-2. Do not simply replace all rules with an LLM: retain deterministic high-confidence handling and use the model as a bounded resolver for ambiguous turns. Do not claim parity with ChatGPT/Gemini internals; reproduce observable engineering principles using our own testable implementation.

## Constraints
- Do not copy proprietary hidden prompts, internal models or private architecture from ChatGPT/Gemini.
- Do not add paid services or subscriptions without explicit approval.
- Do not paste secrets into chat or repository.
- Do not merge or deploy production changes without user approval.
- Do not change production data or schema without a reviewed migration and backup/rollback plan.

## Evidence and status
- Source audited: `app/ai/research.py`, `app/ai/router.py`, `app/main.py`, `app/db.py`, `database/schema.sql`, `tests/test_ai_router.py`.
- Audit status: source inspection completed; runtime/CI execution not yet performed for this branch.
- Current branch starts from production branch `rebuild/master-architecture-v1`.
