alter table public.ai_usage_events
    add column if not exists operation text not null default 'chat_response';
