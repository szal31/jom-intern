-- Run once in the Supabase SQL editor.

create table public.profiles (
  user_id uuid primary key references auth.users on delete cascade,
  data jsonb not null default '{}',
  consent_at timestamptz
);

create table public.packs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  company text, role text, link text,
  status text not null default 'Ready',
  notes text default '',
  files jsonb default '{}',
  created_at timestamptz not null default now()
);

create table public.usage (
  user_id uuid not null references auth.users on delete cascade,
  day date not null,
  packs int not null default 0,
  primary key (user_id, day)
);

-- Errors and checker failures only: never resume or letter text.
create table public.events (
  id bigint generated always as identity primary key,
  kind text, detail text,
  created_at timestamptz not null default now()
);

create table public.jobs (
  id bigint generated always as identity primary key,
  company text, role text, link text, location text,
  posting_text text, date_found date, company_type text
);

alter table public.profiles enable row level security;
alter table public.packs enable row level security;
alter table public.usage enable row level security;
alter table public.events enable row level security;
alter table public.jobs enable row level security;

create policy "own profile" on public.profiles for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own packs" on public.packs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own usage" on public.usage for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "log events" on public.events for insert to authenticated with check (true);
create policy "read jobs" on public.jobs for select to authenticated using (true);

-- At most 10 accounts in the pilot.
create function public.pilot_seats_left() returns int
language sql security definer set search_path = '' as $$
  select greatest(0, 10 - (select count(*)::int from auth.users));
$$;
grant execute on function public.pilot_seats_left() to anon, authenticated;

create function public.enforce_pilot_cap() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if (select count(*) from auth.users) >= 10 then
    raise exception 'pilot_full';
  end if;
  return new;
end;
$$;

create trigger pilot_cap before insert on auth.users
for each row execute function public.enforce_pilot_cap();

-- Private file storage: each student's files live under their own user id.
insert into storage.buckets (id, name, public) values ('packs', 'packs', false);
create policy "own files" on storage.objects for all to authenticated
  using (bucket_id = 'packs' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'packs' and (storage.foldername(name))[1] = auth.uid()::text);
