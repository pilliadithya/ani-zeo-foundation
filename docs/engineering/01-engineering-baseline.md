# Ani Zeo — Engineering Baseline

**Snapshot date:** 2026-11-15  
**Primary repository:** `pilliadithya/ani-zeo-foundation`  
**Production source branch:** `rebuild/master-architecture-v1`  
**Documentation branch:** `docs/engineering-baseline-2026-11-15`  
**Evidence scope:** GitHub repository/PR/CI inspection, Render service/deployment/log inspection, Supabase project/schema/security inspection available during the 2026-11-15 engineering review.

> This is a dated snapshot. Re-check live state before acting. Do not treat unknowns as healthy or failed.

## 1. Repository registry

| Repository | Observed role | Status |
|---|---|---|
| `pilliadithya/ani-zeo-foundation` | Current modular foundation and connected production source | **Verified** |
| `pilliadithya/ani-zeo-bot` | Legacy/original bot; broader historical feature set, largely monolithic | **Verified** |
| `pilliadithya/ani-zeo` | Empty repository/no branches observed during audit | **Verified at snapshot** |

### Foundation branches

The audit observed 28 branches. The production source branch was `rebuild/master-architecture-v1`; other branches contain divergent work. Examples of high divergence from the production source at audit time:

- `feat/provider-independent-conversation-memory`: 25 ahead, 8 behind.
- `feature/ai-token-management-foundation`: 77 ahead, 174 behind.
- `feature/smart-intent-typo-routing`: 20 ahead, 176 behind.
- `fix/ai-reliability-and-webhook-dedup`: 43 ahead, 210 behind.
- `fix/news-claim-attribution-v2`: 60 ahead, 1 behind before its work was merged.

Ahead/behind counts describe Git history divergence only. They do **not** prove feature completion or quality. Review and port changes selectively; do not merge old branches wholesale.

The original bot repository had one `main` branch. No open PRs were observed during the audit. Re-check before creating or merging work.

## 2. Render production service

| Field | Observed value |
|---|---|
| Service | `ani-zeo-foundation` |
| Service ID | `srv-dbl0arugekts73fbefu0` |
| Workspace ID | `tea-dbj1vbou01pc73e8p5c0` |
| URL | https://ani-zeo-foundation.onrender.com |
| Runtime | Python / FastAPI |
| Region | Singapore |
| Plan | Free |
| Instances | 1 |
| Connected repository | `pilliadithya/ani-zeo-foundation` |
| Deploy branch | `rebuild/master-architecture-v1` |
| Auto-deploy | Disabled |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health-check path | Not configured at audit |

### Latest observed deployment

- Deployment ID: `dep-dbsr6f9srm7s73ac3c2g`
- Commit: `fd2f3cf758ebd38fa3290bd6294a0f3eb890f6b1`
- Started: 2026-11-15 13:27 UTC
- Finished approximately: 2026-11-15 13:28 UTC
- Status: **Live** at time of inspection.

This deployment contains PR #26's merged news-attribution safeguards. Live status confirms deployment completion, not full end-to-end correctness.

## 3. Supabase project

| Field | Observed value |
|---|---|
| Project ref | `wgwykuzqjvrsdqrbkfti` |
| Region | Frankfurt (`eu-central-1`) |
| Postgres | 17.11.0.011 |
| Project status | ACTIVE_HEALTHY at audit |

### Migrations observed

1. `20261106171058_allow_failed_telegram_update_status`
2. `20261108135715_create_ai_usage_events`
3. `20261108135944_add_ai_usage_operation`
4. `20261108140132_add_ai_usage_tool_tokens`
5. `20261109112235_ani_zeo_onboarding_and_research_schema`
6. `20261114113252_provider_independent_conversation_memory`

### Tables and approximate observed row counts

| Table | Approx. rows |
|---|---:|
| `user_profiles` | 3 |
| `conversation_messages` | 294 |
| `user_memories` | 1 |
| `processed_telegram_updates` | 176 |
| `ai_usage_events` | 60 |
| `anime_research_evidence` | 26 |
| `conversation_state` | Present; count not captured |

Counts are a point-in-time observation, not guaranteed current. The profile schema includes language preferences, favourites/genres, consent, personalisation and onboarding fields.

### Security observations requiring review

- Seven tables had RLS enabled but no policies. This may be intentional for service-role-only backend access; inspect actual access paths before changing policies.
- `public.rls_auto_enable()` is a SECURITY DEFINER event-trigger function. Its observed ACL included `anon` and `authenticated` EXECUTE. It is an event-trigger function, not an ordinary application RPC. Review whether those grants are necessary; do not call it exploitable based only on this observation.
- Five unused indexes were reported. Do not drop without workload evidence.
- Render is in Singapore while Supabase is in Frankfurt. Measure actual query latency before considering a region change.

No Supabase schema, data, migration, secret or Render setting was modified during this audit.

## 4. Application architecture — observed at snapshot

- FastAPI application entry point: `app.main`.
- Research/provider/FactGuard modules.
- Structured anime API integrations including AniList and Jikan.
- Basic language detection and rule-based intent routing.
- User profiles, conversation history, consent and memory foundations.
- Usage telemetry and evidence archive.

The foundation README described an early milestone rather than a completed product. The legacy bot has more historical features but is monolithic; features should be ported into the modular foundation selectively. Legacy local JSON watchlists/favourites need a deliberate database migration before restoration.

## 5. Provider and environment registry

### Variable names identified in code/config

- `GEMINI_API_KEY`, `GEMINI_API_KEY_2`
- `GROQ_API_KEY`, `GROQ_API_KEY_2`
- `NVIDIA_API_KEY`
- `OPENROUTER_API_KEY`
- `DECODO_API_KEY`
- `LANGSEARCH_API_KEY`
- `TAVILY_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `WEBHOOK_SECRET`
- `DATABASE_URL`
- `AI_PROVIDER_ORDER`
- `AI_TIMEOUT_SECONDS`
- `AI_TOTAL_TIMEOUT_SECONDS`
- `AI_MAX_OUTPUT_TOKENS`
- `SEARCH_PROVIDER_ORDER`
- `AI_COST_RATES_JSON`
- `AI_USAGE_ADMIN_IDS`

**Important:** Render's actual environment variable list and secret values were not available for verification in this review. Presence, validity and current values are **Unknown**. Never paste secret values into this document or chat.

Code/config inspection indicated Gemini and Groq as normal AI provider candidates; NVIDIA and OpenRouter adapters existed but were dormant in the active order at that snapshot. Search integrations included Gemini grounding, Decodo, LangSearch and Tavily. Verify current order and configuration before relying on this.

A configuration mismatch was observed: `.env.example` specified `gemini-3.8-flash`, while `app/config.py` defaulted to `gemini-3.5-flash`; production logs showed `gemini-3.5-flash`. Re-check current files and provider model availability before changing anything.

## 6. Recent merged engineering work

### PR #25 — character question routing

- PR: https://github.com/pilliadithya/ani-zeo-foundation/pull/25
- Title: Restore open-set anime character question routing
- Merge commit: `f2ada7ecec89be7d25c472c18820b34aada25ed6`
- Fixed double-escaped regex word boundaries, allowing fresh-context questions such as “Who is Itachi Uchiha?” and Romanized Telugu “Itachi evaru?” to route into character research.
- CI passed and a deployment was observed on 2026-11-14.

### PR #26 — news claim attribution safeguards

- PR: https://github.com/pilliadithya/ani-zeo-foundation/pull/26
- Title: Prevent anime news story attribution mix-ups
- Feature branch: `fix/news-claim-attribution-v2`
- PR head before merge: `15a1035eb0deba326dbde04cb778ce3703e96d65`
- Squash merge commit: `fd2f3cf758ebd38fa3290bd6294a0f3eb890f6b1`
- Merged: 2026-11-15 13:23:59 UTC
- CI on the exact PR head before merge: two workflows, each reported 194 tests passing.
- Live Render deployment of merge commit was observed afterwards.

Implementation includes URL filtering, page text extraction, story clustering, publisher corroboration, canonical URL deduplication, unsupported number/date/chapter checks, official-confirmation checks, sentence-level source alignment, bounded article retrieval and HTTPS/DNS/redirect/size/timeout safeguards.

Known limitations:
- Lexical source-span alignment is not semantic entailment. It may reject valid paraphrases and may miss subtle contradictions, negation or implication.
- DNS validation followed by HTTP client resolution leaves a possible DNS rebinding gap; production egress restrictions are recommended.
- No end-to-end live-provider test of the merged PR was completed during the audit.

## 7. Production live-search incident observed 2026-11-15

At approximately `2026-11-15T13:29:29Z`, logs for a research request showed:

- Gemini grounded-search account returned HTTP 429; a secondary configured account was tried.
- Gemini model shown in logs: `gemini-3.5-flash`.
- Decodo timed out with a 2.7-second outer budget.
- LangSearch returned no sufficiently relevant anime sources.
- Tavily timed out with a 2.7-second outer budget.
- The bot returned a safe message saying it could not verify the anime information from available sources.

Interpretation:
- The user-facing safe fallback was appropriate.
- HTTP 429 does not by itself prove an invalid key; it may indicate quota, rate limit or account restriction.
- Decodo/Tavily timeout does not prove credentials are invalid.
- A relevance miss is not the same as provider outage.
- Do not claim all provider keys are valid.

### Confirmed timeout design mismatch

In `app/ai/research.py` around line 820 at audit, provider calls were wrapped with an outer wait limit of `min(2.7, remaining)`, while underlying configured client timeouts were longer (Decodo/Tavily 12 seconds, LangSearch 18 seconds). The outer cap can cancel calls before their own timeout is reached.

Recommended engineering direction: design provider-specific budgets under one total request deadline, and consider concurrent/hedged retrieval with cancellation and source-quality controls. Do not simply increase every sequential timeout.

## 8. Phase assessment

| Area | Snapshot assessment |
|---|---|
| Phase 0 — repository/deployment audit | Mostly complete |
| Phase 1 — backend foundation | Implemented; hardening remains |
| Phase 2 — intent understanding | Partially implemented |
| Phase 3 — research and grounding | Implemented, reliability gaps remain |
| Phase 4 — conversation/personality | Partial |
| Phase 5 — provider/token engine | Partial; usage tracking exists |
| Phase 6 — scale and Telegram UX | Partial; durable queue/quota system not proven |
| Phase 7 — legacy feature restoration | Incomplete |
| Phase 8 — evaluation and release testing | Partial; no verified 2,000–5,000-user load test |

These are engineering assessments, not a claim that every listed component was re-tested on this date.

## 9. Priority gaps / risks

1. Research provider orchestration, deadlines and graceful fallback.
2. Semantic claim-level evidence verification and contradiction handling.
3. Provider health, Retry-After handling, circuit breakers and quota tracking.
4. Hybrid intent/entity recognition, typo correction and context resolution.
5. Consistent selected-language and script adherence across every provider.
6. Per-user/global/provider quotas and durable queue/concurrency management.
7. Mature consent-based memory and spoiler/progress protection.
8. Selective restoration of legacy features using database-backed state.
9. Reproducible evaluation benchmark and realistic load tests.
10. Security review of RLS, event-trigger grants, outbound fetch/egress and secret handling.

## 10. Next recommended work

Start with a contained research reliability task:

1. Re-open the current production branch and inspect research orchestration, provider adapters and tests.
2. Reproduce the 2.7-second outer deadline issue with deterministic mocked providers.
3. Design a single total deadline with provider-specific time budgets and bounded concurrency.
4. Preserve relevance filtering, evidence attribution and safe no-evidence fallback.
5. Add tests for timeout, 429/Retry-After, one provider slow/one provider fast, all providers unavailable, cancellation and malformed provider output.
6. Open a PR from a feature branch. Do not deploy until explicitly authorized.

## 11. Explicit unknowns

- Current Render secret presence/validity and actual environment values.
- Current provider quota, billing/account restrictions and live health.
- End-to-end live-provider correctness after PR #26.
- Actual p50/p95 latency and user concurrency capacity.
- Whether all RLS tables are accessed exclusively through service role.
- Actual current number of active users and per-user traffic.
- Completion/quality of old branches and unmerged features.
- Current state after this snapshot date.

## 12. Change log

| Date | Change |
|---|---|
| 2026-11-15 | Initial engineering baseline created from read-only repository, deployment, log and database review. |
