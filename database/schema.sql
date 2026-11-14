create table if not exists public.user_profiles (
  telegram_user_id bigint primary key,
  username text,
  display_name text,
  preferred_language text check (preferred_language in ('tenglish','hinglish','tanglish','english')),
  favorite_anime text,
  favorite_genres text[] not null default '{}',
  consent_version text,
  consented_at timestamptz,
  personalization_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.conversation_messages (
  id bigint generated always as identity primary key,
  telegram_user_id bigint not null references public.user_profiles(telegram_user_id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);
create index if not exists conversation_messages_user_created_idx
  on public.conversation_messages (telegram_user_id, created_at desc);

alter table public.conversation_messages
  add column if not exists telegram_update_id bigint;

create unique index if not exists conversation_messages_user_update_role_uidx
  on public.conversation_messages (telegram_user_id, telegram_update_id, role)
  where telegram_update_id is not null;

create table if not exists public.conversation_state (
  telegram_user_id bigint primary key
    references public.user_profiles(telegram_user_id) on delete cascade,
  active_topic text,
  resolved_entities jsonb not null default '[]'::jsonb,
  last_completed_update_id bigint,
  context_version integer not null default 1,
  updated_at timestamptz not null default now(),
  constraint conversation_state_entities_array
    check (jsonb_typeof(resolved_entities) = 'array')
);
create index if not exists conversation_state_updated_idx
  on public.conversation_state (updated_at desc);
alter table public.conversation_state enable row level security;
revoke all on public.conversation_state from anon, authenticated;
create table if not exists public.user_memories (
  id bigint generated always as identity primary key,
  telegram_user_id bigint not null references public.user_profiles(telegram_user_id) on delete cascade,
  memory_key text not null,
  memory_value text not null,
  confidence text not null default 'explicit' check (confidence in ('explicit','inferred')),
  updated_at timestamptz not null default now(),
  unique (telegram_user_id, memory_key)
);
-- Use this database server-side only. Never expose a privileged database credential to clients.

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
create index if not exists processed_telegram_updates_created_idx
  on public.processed_telegram_updates (created_at);
