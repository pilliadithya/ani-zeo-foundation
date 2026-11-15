# Ani Zeo Engineering Documentation

This directory is the durable engineering handover for Ani Zeo.

## Read in this order

1. [Project vision](00-project-vision.md) — product purpose and non-negotiable principles.
2. [Engineering baseline](01-engineering-baseline.md) — verified repository, deployment, database, architecture, known gaps and risks.
3. [Session handover](02-session-handover.md) — latest known state and recommended next engineering task.
4. [Continuation instructions](CONTINUATION.md) — checklist for any future assistant or contributor.

## Evidence discipline

Every meaningful status must use one of these labels:

- **Verified** — directly confirmed from current source, tool output, tests, or live system.
- **Implemented** — code/schema exists, but runtime behaviour may not yet be fully verified.
- **Partially verified** — some relevant paths or conditions were checked, not all.
- **Failed** — a test or operation was observed to fail.
- **Planned** — intended, not implemented.
- **Unknown** — evidence is unavailable or insufficient.

Always record the evidence date and scope. A passing unit test is not proof of production behaviour. A live deployment is not proof every feature works.

## Safety rules

- Do not deploy, alter production configuration, change secrets, modify production data, or run destructive migrations without explicit authorization.
- Never write secret values into documentation. Record variable names and presence/status only when verified.
- Preserve the current production branch and data. Use a separate branch for documentation and proposed changes.
- Re-check live state before relying on this snapshot; it is a dated handover, not a live dashboard.
