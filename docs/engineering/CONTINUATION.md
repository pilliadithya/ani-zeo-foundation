# Ani Zeo — Continuation Instructions

You are continuing the Ani Zeo engineering project.

## Mandatory onboarding

Before proposing implementation or making changes:

1. Read `docs/engineering/00-project-vision.md`.
2. Read `docs/engineering/01-engineering-baseline.md`.
3. Read `docs/engineering/02-session-handover.md`.
4. Inspect the actual GitHub repository, current production branch and latest commits.
5. Re-check Render deployment/service state and Supabase state when relevant.
6. Compare the live code and infrastructure against the dated documentation. Update the baseline if facts have changed.

## Source-of-truth rules

- Actual current code and live system evidence outrank this handover.
- The handover is a snapshot, not proof of present state.
- Never assume a planned feature is implemented.
- Never claim tests, CI, deployment or provider credentials succeeded without direct evidence.
- Distinguish unit tests, integration tests and live end-to-end tests.
- Preserve explicit uncertainty and list unknowns.

## Change-control rules

- Do not deploy or change production configuration, secrets, database schema or production data without explicit authorization.
- Prefer isolated feature branches and pull requests.
- Do not merge divergent historical branches wholesale.
- Never expose API keys, bot tokens, database URLs or other secrets.
- Do not weaken evidence, relevance, privacy or spoiler safeguards to make a response appear successful.
- For every meaningful change, add tests, report their exact scope/results and update the handover.

## Engineering objective

Build Ani Zeo as a reliable, personalised, multilingual Anime Intelligence Companion—not merely a Telegram chatbot.

The product must be accurate before fluent, respect the user's selected language and script, cite evidence for factual research, disclose uncertainty, remember only with consent, and degrade safely when sources or providers fail.

## Current suggested starting point

Re-check the research provider timeout orchestration described in the latest Session Handover. Confirm the issue still exists before implementing a fix. Do not blindly apply the old diagnosis if the code has changed.
