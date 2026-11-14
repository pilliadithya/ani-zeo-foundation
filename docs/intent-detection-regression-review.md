# Intent Detection Regression Review

Date: 2026-11-14
Production branch: `rebuild/master-architecture-v1`

## Executive finding

The Itachi Uchiha incident was caused by a regression in the deterministic scope gate, not by Telegram delivery, an AI provider, AniList, or search.

Render logged the request at 2026-11-14 12:42:23 UTC as:
`Intent detected (intent=unclear, scope=redirect, confidence=0.55)`
The webhook then returned HTTP 200 at 12:42:24 UTC. The handler's `scope == "redirect"` branch replied with the generic anime-only message and returned before metadata, research, or AI generation.

## Production change chronology

1. `9266dbffa979cc0ed0d5963f86f062286ea33206` — "Fix character question title routing". Removed `who is` from the `TITLE` extraction regex. This was correct: "Who is Naruto?" and "Who is Luffy's father?" must not be sent to AniList as anime-title lookups. Added tests that `extract_title("Who is Naruto?")` is None.
2. `94f6df279e91fdd03d70732ea1314d929d149f49` — "Make Ani Zeo companion-first and concise by default". Kept simple character facts conversational (1–3 short sentences), removed forced character dossier formatting, limited default emoji, and made saved language preference authoritative. These are valuable UX changes and must be preserved.
3. `84fe82ab228fe39db0cf98a82ec923effc3328c1` — merge of PR #24, "Fix multilingual anime intent detection without changing chat flow". Added bounded recent context, stale-context blocking, multilingual follow-up cues, and explicit off-topic handling. However, it changed the scope gate so character intent only entered anime scope when the message also matched a manually maintained anime entity/vocabulary list or recent anime context. The list omitted Itachi Uchiha. Thus "Who is Itachi Uchiha?" became `unclear/redirect`.

## Before vs after

### Before PR #24 (94f6df2)

- Character question shapes such as "Who is ..." were classified as `character_question` even if the named character was not in the entity allowlist.
- The earlier title-routing correction kept "Who is ..." out of the AniList anime-title extraction path.
- Weakness: broad character-shaped prompts could be treated as anime without strong evidence; explicit off-topic protection still existed but was keyword-based.

### After PR #24 (84fe82a)

- Follow-up context became more bounded and safer against stale anime context.
- English, Tenglish and Telugu follow-up patterns improved.
- Explicit off-topic requests were prioritised.
- Regression: character intent was gated by `anime_scope`, while `anime_scope` depended on a limited hardcoded entity list, anime vocabulary or context. Unknown/new character names were rejected before the answer pipeline.

## Corrected design

- Keep intent detection, entity recognition, title extraction, context resolution and routing conceptually separate.
- A clear character-question form is an anime-domain candidate even when the character name is unfamiliar. A manually curated character allowlist must not be a hard prerequisite.
- Explicit off-topic indicators still take precedence.
- Keep `extract_title` independent: character questions must not become AniList title lookups.
- Preserve bounded context and stale-context protections from PR #24.
- Preserve concise companion-style answers and the saved-language preference from 94f6df2.
- Do not treat a keyword/regex detector as a universal entity resolver. Future work can add structured character search/entity resolution, but it must fail gracefully and not block a plausible character question.

## Current corrective change

This branch restores open-set character-question routing by allowing a recognised character-question shape to establish anime scope, while the explicit off-topic check still runs first. It also recognises common Tenglish/Telugu "who" forms (`evaru`, `evadu`, `ఎవరు`, `ఎవడ`).

Regression tests cover:
- Fresh-context "Who is Itachi Uchiha?"
- Kakashi Hatake, Madara Uchiha and the Akatsuki
- Tenglish and Telugu-script character questions
- Character questions not being extracted as anime titles
- Explicit off-topic programming requests still taking precedence
- Existing multilingual follow-up, topic-switch and stale-context tests

## External design research

The implementation direction follows established NLU design patterns:
- Dialogflow CX describes intent as the user's intention for one turn, uses training phrases to generalise beyond exact examples, and treats parameters as separate extracted values. It also uses a classification threshold for no-match outcomes.
- Rasa's fallback guidance describes graceful low-confidence handling, including clarification rather than an immediate hard rejection.
- Dialogflow's agent design guidance recommends avoiding overlapping intent definitions and using production no-match observations to improve coverage.

References:
- https://cloud.google.com/dialogflow/cx/docs/concept/intent
- https://cloud.google.com/dialogflow/cx/docs/concept/agent-settings
- https://legacy-docs-oss.rasa.com/docs/rasa/fallback-handoff/
- https://cloud.google.com/dialogflow/cx/docs/concept/agent-design

## Validation status

The code and regression tests are committed to this review branch. CI must pass before merge. This is not a claim of perfect intent recognition. The production Telegram bot must be tested with a representative multilingual golden set after an approved deployment.

## Production safety

No Render settings, Supabase data, migrations, secrets, or production deployment are changed by this PR. Merge and deployment remain separate release decisions.
