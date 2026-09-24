-- SignalStack: each user's tracked jobs.
-- Paste this whole file into the Supabase SQL editor and run it. It is safe to run again.

-- ---------- Table ----------
-- One row per user per job. The job itself lives in site/data.json; "job" keeps a copy of its
-- title, company, link and so on, so a tracked job still shows after it drops out of the daily data.
create table if not exists public.tracked_jobs (
  user_id    uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  job_id     text        not null check (char_length(job_id) between 1 and 100),
  status     text        not null default 'saved'
                         check (status in ('saved', 'applied', 'interviewing', 'offer', 'rejected')),
  note       text        not null default '' check (char_length(note) <= 500),
  job        jsonb       check (job is null or octet_length(job::text) <= 4000),
  saved_at   timestamptz not null default now(),
  applied_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, job_id)
);

comment on table public.tracked_jobs is 'Jobs each user has saved or applied to, with status and notes.';

-- ---------- Timestamps ----------
-- updated_at changes on every edit, saved_at never changes after the first save,
-- and applied_at is set the first time the status moves past "saved".
create or replace function public.tracked_jobs_set_times()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' then
    new.updated_at := now();
    new.saved_at := old.saved_at;
  end if;
  if new.status <> 'saved' and new.applied_at is null then
    new.applied_at := now();
  end if;
  return new;
end;
$$;

drop trigger if exists tracked_jobs_set_times on public.tracked_jobs;
create trigger tracked_jobs_set_times
  before insert or update on public.tracked_jobs
  for each row execute function public.tracked_jobs_set_times();

-- ---------- Row Level Security ----------
alter table public.tracked_jobs enable row level security;

drop policy if exists "Users can read their own tracked jobs"   on public.tracked_jobs;
drop policy if exists "Users can add their own tracked jobs"    on public.tracked_jobs;
drop policy if exists "Users can change their own tracked jobs" on public.tracked_jobs;
drop policy if exists "Users can delete their own tracked jobs" on public.tracked_jobs;

create policy "Users can read their own tracked jobs"
  on public.tracked_jobs for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can add their own tracked jobs"
  on public.tracked_jobs for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can change their own tracked jobs"
  on public.tracked_jobs for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their own tracked jobs"
  on public.tracked_jobs for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------- Grants ----------
-- New tables are not exposed to the API automatically in this project, so grant access here.
-- Only signed-in users get access; guests (anon) get none. RLS above limits each user to their own rows.
revoke all on table public.tracked_jobs from anon, authenticated;
grant select, insert, update, delete on table public.tracked_jobs to authenticated;
