# Ani Zeo AI Engine v2

## Request pipeline

1. Intent detection and conservative typo correction.
2. Conversation history and relevant user memory selection.
3. Adaptive input/output token budgeting.
4. Current anime research through Gemini Google Search, with Tavily as a sequential fallback.
5. Evidence screening and provenance labels.
6. A shared AI conversation writer for both live-search providers.
7. Deterministic post-generation checks for unsupported chapter identifiers, dates, official-confirmation language, and conflicting chapter dates.
8. Telegram formatting and compact source links.
9. Privacy-preserving token and latency telemetry.

## Evidence labels

- `primary_source`: source domain is in the maintained primary-source allowlist.
- `reputable_reporting`: source domain is in the maintained news-publication allowlist.
- `unverified_publisher`: relevant HTTPS source, but not in either allowlist.
- `google_grounding_claim_support_passed`: Gemini supplied a source-linked claim span; source provenance is still classified separately.

A search snippet is not proof of an official announcement. The final writer must distinguish primary-source confirmation from reporting and unverified material. Conflicting dates associated with the same chapter are passed to the writer and blocked if the final answer repeats a date for that chapter.

The deterministic final verifier is deliberately conservative. It checks chapter numbers, explicit dates and official-confirmation wording. It is not a general semantic theorem prover; source-grounding and provenance checks remain essential.

## Token management

- Stable system prompt is compressed to reduce repeated input.
- Recent history, memory and research context have explicit character budgets.
- Input token estimates use UTF-8 byte length divided by four. This is a planning estimate, not a provider tokenizer.
- Provider-reported usage is authoritative when returned.
- Output budgets adapt to request depth and are capped by `AI_MAX_OUTPUT_TOKENS`.
- Usage records retain input, output, cached, thinking and tool-use counts when providers expose them.
- Failed/missing usage is stored as unknown, not fabricated as zero.
- Memory summaries use a smaller output budget.
- Live Gemini grounding and the final response-writer call are logged as separate operations.

## Cost estimates

Set `AI_COST_RATES_JSON` only with current pricing for the exact provider/model. Rates are USD per one million tokens. Example:

```json
{
  "gemini-2.5-flash": {
    "input_per_million_usd": 0.0,
    "output_per_million_usd": 0.0
  }
}
```

The zeroes are placeholders, not pricing advice. Leave the setting empty to disable cost estimates. Thinking and tool-use tokens are included in the relevant input/output estimate. If rates are unavailable, cost remains null.

## Usage telemetry

The `public.ai_usage_events` table stores counts, provider/model, operation, latency, finish reason and optional estimated cost. It never stores prompts or generated answers.

The `/aiusage` command reports aggregate usage over seven days. It is disabled unless `AI_USAGE_ADMIN_IDS` contains a comma-separated allowlist of Telegram user IDs.

## Database migrations

- `002_ai_usage_events.sql`: usage telemetry table.
- `003_ai_usage_operation.sql`: operation labels.
- `004_ai_usage_tool_tokens.sql`: tool-use token counts.

These additive migrations were applied to the connected Supabase project. RLS is enabled without public policies, so the table is not exposed to anon/authenticated API roles; the bot uses its server-side database connection.

## Operational safeguards

- Usage persistence errors never fail a user-facing answer.
- Live requests fail closed when current evidence is unavailable.
- Tavily snippets are never sent directly as the final user response; they pass through the shared writer.
- The admin usage command requires an explicit allowlist.
- No environment variable is required for the new code to start. Pricing estimates and the admin command remain opt-in.
