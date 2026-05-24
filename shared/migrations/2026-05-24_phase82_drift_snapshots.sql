-- Phase 8.2-P2: drift_snapshots — Score-Drift-Monitoring persistiert.
-- In Supabase ausführen: SQL Editor → New Query → Paste → Run.

create table if not exists drift_snapshots (
    id                 uuid primary key default uuid_generate_v4(),
    run_id             uuid references crawl_runs (id) on delete cascade,
    timestamp          timestamptz not null default now(),
    n_scored           int not null default 0,
    n_kept             int not null default 0,
    n_gold             int not null default 0,
    posterior_min      numeric(8,5),
    posterior_max      numeric(8,5),
    posterior_mean     numeric(8,5),
    posterior_median   numeric(8,5),
    posterior_p95      numeric(8,5),
    tier_counts        jsonb not null default '{}'::jsonb,
    gold_sample_ids    jsonb not null default '[]'::jsonb,
    gold_sample_reasons jsonb not null default '[]'::jsonb,
    alert              jsonb,                          -- null = kein drift
    created_at         timestamptz not null default now()
);

create index if not exists drift_snapshots_timestamp_idx
    on drift_snapshots (timestamp desc);

create index if not exists drift_snapshots_alert_idx
    on drift_snapshots ((alert is not null))
    where alert is not null;

-- RLS: nur Admin lesen, alle authenticated dürfen schreiben (über service_role)
alter table drift_snapshots enable row level security;

create policy drift_admin_read on drift_snapshots
    for select using (
        exists (
            select 1 from profiles
            where id = auth.uid() and role = 'admin'
        )
    );
