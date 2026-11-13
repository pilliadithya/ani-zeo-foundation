# Bytez AI — Reserved Provider Slot

Status: **Planned / disabled / no API key configured**

This document reserves a place for Bytez in Ani Zeo. It does not enable Bytez, make network calls, or require credentials.

## Reserved configuration

- Provider ID: `bytez`
- Display name: `Bytez AI`
- Enabled by default: `false`
- API key environment variable (reserved): `BYTEZ_API_KEY`
- Model selection: to be decided after account setup and benchmarking
- Routing priority: unset until tested and explicitly approved

## Activation requirements

Before implementation or activation:
1. Confirm the current official API endpoint, authentication method, SDK/API contract, and supported chat models.
2. Verify free-tier eligibility, limits, expiry, and whether a payment method is required.
3. Review data-retention and privacy terms.
4. Add an adapter with timeouts, bounded retries, normalized errors, and usage telemetry.
5. Benchmark anime factuality, Tenglish/Roman Telugu quality, latency, rate limits, and cost.
6. Add deterministic tests for success, missing credentials, rate limits, timeouts, malformed output, and provider failure.

Until those checks pass, Bytez must not receive production traffic.
