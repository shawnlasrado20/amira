-- Run this once in Supabase Dashboard -> SQL Editor.
-- It creates Amira's first multi-tenant schema and locks every row to its owner.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null default '',
  business_name text not null default '',
  phone text not null default '',
  plan text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.assistants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  config jsonb not null default '{}'::jsonb,
  browser_state jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists assistants_user_id_idx on public.assistants(user_id);

alter table public.profiles enable row level security;
alter table public.assistants enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles for select to authenticated
using ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles for update to authenticated
using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

drop policy if exists "assistants_select_own" on public.assistants;
create policy "assistants_select_own" on public.assistants for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "assistants_insert_own" on public.assistants;
create policy "assistants_insert_own" on public.assistants for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "assistants_update_own" on public.assistants;
create policy "assistants_update_own" on public.assistants for update to authenticated
using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists "assistants_delete_own" on public.assistants;
create policy "assistants_delete_own" on public.assistants for delete to authenticated
using ((select auth.uid()) = user_id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, email, business_name, phone)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'business_name', ''),
    coalesce(new.raw_user_meta_data ->> 'phone', '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

-- Backfill a profile for any account created before this schema was installed.
insert into public.profiles (id, email, business_name, phone)
select id, coalesce(email, ''), coalesce(raw_user_meta_data ->> 'business_name', ''),
       coalesce(raw_user_meta_data ->> 'phone', '')
from auth.users
on conflict (id) do nothing;
