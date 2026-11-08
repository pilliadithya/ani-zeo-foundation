alter table public.ai_usage_events
    add column if not exists tool_tokens integer;
