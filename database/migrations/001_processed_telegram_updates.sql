-- Durable Telegram webhook idempotency.
-- Safe to run repeatedly on an existing Supabase/PostgreSQL database.
create table if not exists public.processed_telegram_updates (
  update_id bigint primary key,
  status text not null default 'processing'
    check (status in ('processing', 'completed', 'failed')),
  attempts integer not null default 1 check (attempts > 0),
  claimed_at timestamptz not null default now(),
  completed_at timestamptz,
  last_error text,
  created_at timestamptz not null default now()
);

create index if not exists processed_telegram_updates_created_idx
  on public.processed_telegram_updates (created_at);
