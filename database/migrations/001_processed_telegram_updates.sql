-- Durable Telegram webhook idempotency.
-- Safe for fresh installs and upgrades of the earlier Foundation table.
-- Existing update rows and legacy columns are preserved.

create table if not exists public.processed_telegram_updates (
  update_id bigint primary key,
  claim_token uuid not null default gen_random_uuid(),
  status text not null default 'processing'
    check (status in ('processing', 'completed', 'failed')),
  attempts integer not null default 1 check (attempts > 0),
  claimed_at timestamptz not null default now(),
  completed_at timestamptz,
  last_error text,
  created_at timestamptz not null default now()
);

-- Add every column used by the current application to pre-existing tables.
alter table public.processed_telegram_updates
  add column if not exists claim_token uuid,
  add column if not exists status text not null default 'processing',
  add column if not exists attempts integer not null default 1,
  add column if not exists claimed_at timestamptz not null default now(),
  add column if not exists completed_at timestamptz,
  add column if not exists last_error text,
  add column if not exists created_at timestamptz not null default now();

-- Backfill tokens before enforcing NOT NULL. gen_random_uuid() is built into
-- supported PostgreSQL versions used by Supabase.
update public.processed_telegram_updates
set claim_token = gen_random_uuid()
where claim_token is null;

alter table public.processed_telegram_updates
  alter column claim_token set default gen_random_uuid(),
  alter column claim_token set not null,
  alter column status set default 'processing',
  alter column attempts set default 1,
  alter column claimed_at set default now(),
  alter column created_at set default now();

create index if not exists processed_telegram_updates_created_idx
  on public.processed_telegram_updates (created_at);
