create table if not exists public.anime_research_evidence (
  id bigint generated always as identity primary key,
  source_url text not null unique,
  source_domain text not null,
  title text not null,
  snippet text not null,
  published_at text,
  verification_status text not null
    check (verification_status in (
      'primary_source',
      'reputable_reporting',
      'unverified_publisher',
      'grounding_support_passed'
    )),
  provider text not null,
  first_seen_at timestamptz not null default now(),
  last_verified_at timestamptz not null default now()
);

alter table public.anime_research_evidence enable row level security;

create index if not exists anime_research_evidence_last_verified_idx
  on public.anime_research_evidence (last_verified_at desc);

create index if not exists anime_research_evidence_search_idx
  on public.anime_research_evidence using gin (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(snippet, ''))
  );

comment on table public.anime_research_evidence is
  'Global anime research archive containing short source excerpts and provenance, never user conversation text.';
