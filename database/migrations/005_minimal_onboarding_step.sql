alter table public.user_profiles
  add column if not exists onboarding_step text not null default 'welcome';

alter table public.user_profiles
  drop constraint if exists user_profiles_onboarding_step_check;

alter table public.user_profiles
  add constraint user_profiles_onboarding_step_check
  check (onboarding_step in (
    'welcome',
    'awaiting_name',
    'awaiting_language',
    'completed',
    'declined'
  ));

-- Preserve existing consenting users without forcing them through onboarding again.
update public.user_profiles
set onboarding_step = case
  when consented_at is not null and preferred_language is not null then 'completed'
  when consented_at is not null then 'awaiting_language'
  else 'welcome'
end
where onboarding_step = 'welcome'
  and consented_at is not null;
