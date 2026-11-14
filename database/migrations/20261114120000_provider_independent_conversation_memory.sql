-- Provider-independent canonical conversation state.
-- Existing transcript and summaries remain intact; all additions are backward-compatible.
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
