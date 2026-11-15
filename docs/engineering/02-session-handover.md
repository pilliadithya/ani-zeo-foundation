# Ani Zeo — Session Handover

**Last reviewed:** 2026-11-15  
**Current production branch:** `rebuild/master-architecture-v1`  
**Current documentation branch:** `docs/engineering-baseline-2026-11-15`  
**Production deployment observed:** `dep-dbsr6f9srm7s73ac3c2g` at commit `fd2f3cf758ebd38fa3290bd6294a0f3eb890f6b1`

## Where the project stands

Ani Zeo has moved from the old monolithic bot toward a modular FastAPI + Supabase foundation. The latest observed production deployment includes PR #26's news-attribution safeguards. Character question routing from PR #25 is also merged and was deployed.

The foundation is not yet a finished, production-hardened anime companion. Intent understanding, research reliability, conversation quality, provider orchestration, quotas/queueing, feature restoration and evaluation still need work.

## Most important confirmed issue

Live research logs showed provider failures/timeouts and a safe no-evidence response. A concrete design issue was identified: provider calls are capped externally at 2.7 seconds even though some underlying provider clients are configured for 12–18 seconds. This may cancel providers before their own timeout can complete.

The next recommended task is to inspect the current branch and build a tested provider deadline/orchestration improvement. Preserve evidence relevance and safe fallback behaviour.

## Immediate next steps

- [ ] Re-check production branch HEAD and deployment status.
- [ ] Re-read current `app/ai/research.py`, provider adapters, configuration and related tests; confirm the 2.7-second cap still exists.
- [ ] Reproduce the issue with deterministic mocked providers.
- [ ] Design provider-specific time budgets inside one total deadline.
- [ ] Test concurrent/hedged retrieval only if it can preserve relevance, cancellation and evidence safeguards.
- [ ] Add tests for timeout, 429/Retry-After, mixed provider latency, all providers failing, cancellation and invalid output.
- [ ] Open a feature branch and PR; do not deploy without explicit authorization.

## Guardrails

- Do not modify production data, database schema, secrets or Render configuration as part of this task.
- Do not merge or deploy without explicit authorization.
- Do not assume environment variables are present or valid.
- Do not interpret branch divergence as feature completion.
- Update this handover after each meaningful engineering milestone.

## Important references

- Foundation repo: https://github.com/pilliadithya/ani-zeo-foundation
- Legacy bot repo: https://github.com/pilliadithya/ani-zeo-bot
- PR #25: https://github.com/pilliadithya/ani-zeo-foundation/pull/25
- PR #26: https://github.com/pilliadithya/ani-zeo-foundation/pull/26
- Render service: https://ani-zeo-foundation.onrender.com

For detailed evidence and caveats, read [Engineering Baseline](01-engineering-baseline.md).
