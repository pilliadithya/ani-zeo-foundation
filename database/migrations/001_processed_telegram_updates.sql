-- Durable Telegram webhook idempotency.
-- Compatible with both fresh databases and the earlier Foundation table
-- (which may already contain claim_token and lack attempts/last_error/created_at).

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

-- Upgrade an existing table without dropping data or legacy columns.
alter table public.processed_telegram_updates
  add column if not exists attempts integer not null default 1,
  add column if not exists last_error text,
  add column if not exists created_at timestamptz not null default now();

create index if not exists processed_telegram_updates_created_idx
  on public.processed_telegram_updates (created_at);
