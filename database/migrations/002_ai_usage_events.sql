-- Privacy-preserving provider usage telemetry.
-- Stores counts and performance metadata only; never prompts or model responses.
create table if not exists public.ai_usage_events (
    id bigserial primary key,
    telegram_user_id bigint,
    provider text not null,
    model text,
    input_tokens integer,
    output_tokens integer,
    total_tokens integer,
    cached_input_tokens integer,
    thinking_tokens integer,
    estimated_input_tokens integer,
    latency_ms integer,
    finish_reason text,
    created_at timestamptz not null default now(),
    constraint ai_usage_nonnegative_tokens check (
        (input_tokens is null or input_tokens >= 0) and
        (output_tokens is null or output_tokens >= 0) and
        (total_tokens is null or total_tokens >= 0) and
        (cached_input_tokens is null or cached_input_tokens >= 0) and
        (thinking_tokens is null or thinking_tokens >= 0) and
        (estimated_input_tokens is null or estimated_input_tokens >= 0) and
        (latency_ms is null or latency_ms >= 0)
    )
);

create index if not exists ai_usage_events_created_at_idx
    on public.ai_usage_events (created_at desc);
create index if not exists ai_usage_events_user_created_at_idx
    on public.ai_usage_events (telegram_user_id, created_at desc);

alter table public.ai_usage_events enable row level security;
