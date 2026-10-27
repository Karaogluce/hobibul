-- ============================================================
-- Hobi Bul — analitik şeması
-- Supabase projesi oluşturduktan sonra bu dosyanın TAMAMINI
-- "SQL Editor" bölümünde çalıştırın (New query → Run).
-- ============================================================

-- 1) Olay tablosu: sayfa görüntülenme ve affiliate tıklamaları
create table if not exists public.analytics_events (
  id bigint generated always as identity primary key,
  event_type text not null check (event_type in ('pageview', 'click')),
  page text not null default '',
  product_id text,
  network text,
  referrer text,
  created_at timestamptz not null default now()
);

create index if not exists analytics_events_type_idx on public.analytics_events (event_type);
create index if not exists analytics_events_page_idx on public.analytics_events (page);
create index if not exists analytics_events_created_idx on public.analytics_events (created_at);

-- 2) Özet görünümler (dashboard için; isteğe bağlı ama önerilir)
create or replace view public.dashboard_stats as
select
  page,
  count(*) filter (where event_type = 'pageview') as views,
  count(*) filter (where event_type = 'click') as clicks
from public.analytics_events
group by page;

create or replace view public.product_clicks as
select
  product_id,
  count(*) as clicks
from public.analytics_events
where event_type = 'click' and product_id is not null
group by product_id;

-- 3) Satır düzeyi güvenlik: anon anahtarın yazma ve okuma yetkisi
alter table public.analytics_events enable row level security;

drop policy if exists "anon insert events" on public.analytics_events;
create policy "anon insert events" on public.analytics_events
  for insert to anon with check (true);

drop policy if exists "anon select events" on public.analytics_events;
create policy "anon select events" on public.analytics_events
  for select to anon using (true);

-- ============================================================
-- NOT: anon (public) anahtar herkese açıktır; teorik olarak isteyen
-- sahte olay yazabilir. Küçük bir site için önemsizdir. Daha sıkı
-- güvenlik isterseniz yazmayı bir sunucuya (service_role) taşıyın ve
-- anon için yalnızca "select" bırakın.
-- ============================================================
