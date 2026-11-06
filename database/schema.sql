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


-- Persistent Telegram webhook deduplication.
create table if not exists public.processed_telegram_updates (
  update_id bigint primary key,
  status text not null check (status in ('processing','completed')),
  claimed_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists processed_telegram_updates_claimed_idx
  on public.processed_telegram_updates (claimed_at);
