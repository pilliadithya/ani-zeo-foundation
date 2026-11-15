# Full Conversation Intelligence and Multilingual Understanding

Status: research-backed implementation plan plus first continuity slice on branch feat/full-multilingual-conversation-intelligence-v1.

## Product requirements
- Understand natural requests and follow-ups without requiring slash commands.
- Silently correct obvious typos while preserving intended meaning, unfamiliar names, slang and code-switching.
- Handle English, Telugu script, Romanized Telugu/Tenglish, Hindi/Hinglish, Tamil/Tanglish and other languages where models have evidence of support.
- Preserve saved response-language preference. Do not change output language merely because a message mentions another language.
- Resolve pronouns, ellipsis, corrections, topic switches and multi-entity references.
- Unknown intent is not automatically off-topic. Clarify only when necessary.
- Deterministic follow-up handling must survive provider outages.
- Non-consented users receive volatile, short-lived context only: no Postgres, long-term memory, prompt logs, analytics or summaries.
- No model/library enters the production dependency path without license, resource, privacy and CI review.

## Research: reusable public systems

### Indic language and code-mix resources
1. AI4Bharat IndicLID — https://github.com/AI4Bharat/IndicLID
   - Identifies 22 Indic languages in native and Roman scripts, including Telugu Latin (tel_Latn), Hindi Latin (hin_Latn) and English.
   - Two-stage design: fast linear classifier plus slower LM classifier.
   - Published Roman-script ensemble accuracy is about 0.80, so treat as a signal, not an oracle.
   - MIT code/model license per repository. Full BERT model is reported around 1.4 GB and 10 sentences/sec; not suitable for the current Render free web instance. Evaluate compact model or separate service only after profiling.
2. AI4Bharat IndicXlit — https://github.com/AI4Bharat/IndicXlit
   - About 11M parameters; transliterates between Roman and native scripts for 21 Indic languages, including Telugu and Hindi.
   - Trained on Aksharantar. It is a transliterator, not an intent detector or typo corrector. Named-entity accuracy is weaker than ordinary-word accuracy. Never transliterate a whole mixed-language sentence blindly; preserve English terms and anime names.
   - Repository is MIT; verify model/data terms independently before bundling.
3. AI4Bharat IndicTrans2 — https://github.com/AI4Bharat/IndicTrans2
   - Translation across 22 scheduled Indic languages; MIT repository/model license.
   - Translation is not typo correction or intent classification. Keep it out of the normal chat hot path.
4. fastText language identification — https://fasttext.cc/docs/en/language-identification
   - Compressed lid.176.ftz model is 917 kB and identifies 176 languages including Telugu and Hindi.
   - Standard-text model, not a reliable Romanized Telugu/Hinglish detector. Model license CC-BY-SA 3.0.
5. LanguageTool — https://help.languagetool.org/hc/en-us/articles/39254526141463-What-languages-does-LanguageTool-support
   - Useful grammar/spelling tool for supported languages, but the current free-language list does not include Telugu or Hindi. Not a solution for Romanized Telugu.

### General multilingual models
1. Qwen3 — https://github.com/QwenLM/Qwen3
   - Open weights under Apache 2.0 per official repository; 119 languages and dialects including English, Hindi, Telugu and other Dravidian languages.
   - Candidate for a future specialist intent/normalization model. An 8B model still needs meaningful RAM/VRAM and should not be loaded into the current Render web process.
2. Gemma 3 — https://ai.google.dev/gemma/docs/core/model_card_3
   - Open weights under Google's Gemma terms; model card reports 140+ languages, multimodal input and 128K context.
   - Candidate model, but broad language coverage is not proof of equal Romanized Telugu quality.
3. Aya Expanse — https://docs.cohere.com/docs/aya-expanse
   - 32B model optimized for 23 listed languages including Hindi and English. Telugu is not on that optimized list; too large for current free infrastructure.
4. Existing Gemini/Groq/NVIDIA/OpenRouter chain
   - Already integrated. Use existing configured providers for uncertain normalization; do not require another key or assume free quotas are permanent.
   - Gemini multi-turn guidance recommends sending relevant message history and context: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/chat/chat-prompts

### Conversation architecture patterns
- Rasa fallback uses confidence thresholds and ambiguity margins; low-confidence turns can enter clarification/rephrase instead of being forced into a wrong intent: https://legacy-docs-oss.rasa.com/docs/rasa/next/fallback-handoff/
- Rasa also documents LLM-based intent classification against a bounded intent domain: https://legacy-docs-oss.rasa.com/docs/rasa/next/llms/llm-intent/
- Multi-turn assistants use a selected history window plus structured context; sending every past message is unnecessary and often counterproductive.

## Target pipeline
1. Input normalization: Unicode normalization, whitespace cleanup, bounded input. Preserve original text separately from normalized query. Protect anime titles, character/creator/studio names, handles, code, URLs and quoted text.
2. Language/script signal: saved language controls output; infer input script using Unicode and low-cost Romanized Telugu/Hindi/Tamil patterns. IndicLID may be optional behind a flag after resource profiling. Never require an external language API.
3. Typo/transliteration: exact alias and keyboard corrections first; fuzzy correction only against domain lexicon with conservative score/margin; model-assisted correction for uncertain Romanized/code-mixed text. IndicXlit may generate alternate-script candidates only, never replace the user's language.
4. Intent/entities: bounded intent labels (anime info, character, recommendation, watch/read order, trailer/media, airing/news, studio/creator, manga, Ani Zeo help, greeting, explicit off-topic, unclear). Resolve references against active topic/entities and recent turns. Explicit topic switches win. Unknown anime titles must not be labelled off-topic merely because unseen.
5. Conversation state:
   - Consented users: existing DB transcript/state/memory path.
   - Non-consented users: volatile RAM-only context per Telegram user, TTL 20 minutes, max 8 turns, max 500 active users, bounded text. Never persist to DB, logs, analytics or summaries. It is lost on process restart/new instance by design.
   - Clear volatile context on explicit off-topic, /newchat, deletion or expiry.
6. Response: normalized request + small relevant history + structured topic/entities/task + saved language/spoiler policy. Ground factual anime metadata in AniList/Jikan/research evidence.
7. Fallback: deterministic high-confidence follow-ups work even when all model providers fail. AI resolver runs only for uncertain turns with strict timeout/token/schema validation. If still unclear, ask one targeted question.

## Implementation stages
- CI-1 (this branch): volatile continuity for non-consented users; typo-aware follow-up; expiry, isolation, size bounds and off-topic reset.
- CI-2: typed ConversationContext snapshot: active topic, canonical IDs, entities, last intent, unresolved task, correction, topic age and provenance.
- CI-3: normalization adapter with protected spans, Romanized Telugu/Tenglish and Hinglish/Tanglish patterns, language/script hints, deterministic correction and model rewrite.
- CI-4: intent/entity schema, topic-switch precedence, confidence calibration and deterministic fallback.
- CI-5: multilingual regression corpus and evaluation: English typos, English-Hindi mix, Telugu script, Romanized Telugu variants, anime names, follow-ups, corrections, ambiguous references and off-topic switches.
- CI-6: optional IndicLID/IndicXlit behind flags after load tests; optional Qwen3/Gemma only with real affordable inference or dedicated hardware.
- CI-7: canary and Telegram acceptance tests; measure latency, false redirects, wrong-topic carryover and language adherence.

## Evaluation
Track intent accuracy/macro-F1/confusion matrix, follow-up entity resolution, typo correction precision (especially false corrections of proper nouns), language/script identification, topic-switch false carryover, false redirect/clarification rate, saved-language adherence, p50/p95 latency and provider-failure recovery.
Do not claim ChatGPT/Gemini parity from a small test suite. Use synthetic labelled cases and opt-in anonymized feedback only; never use non-consented conversations for training/analytics.

## Current implementation
- app/main.py: bounded volatile context helpers for non-consented users; clear after explicit off-topic.
- app/ai/research.py: typo vocabulary and 'its' follow-up recognition from PR #30.
- Tests cover context isolation, TTL, bounds and invalid roles. Broader multilingual evaluation remains next.

## Deployment constraints
Render free is not a suitable host for multi-GB language-ID models or an 8B LLM. Keep hot path lightweight and use existing providers for uncertain cases. Do not install PyTorch/Transformers, download weights at startup, or add paid external endpoints without explicit cost and deployment review.
