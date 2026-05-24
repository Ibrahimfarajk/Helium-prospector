-- ═══════════════════════════════════════════════════════════════════════
-- helium-prospector — Postgres-Schema (Supabase)
-- Stand: 2026-05-24, V2.3-Architektur
-- ═══════════════════════════════════════════════════════════════════════
--
-- Konventionen:
-- - Alle Tabellen: id (uuid pk), created_at, updated_at
-- - Soft-Delete via deleted_at (für DSGVO-Recovery + Audit)
-- - RLS aktiv auf allen tabellen mit Personen-Daten
-- - Trigger: updated_at automatisch
-- ═══════════════════════════════════════════════════════════════════════

create extension if not exists "uuid-ossp";
create extension if not exists "pg_trgm";   -- für Volltext-Suche

-- ───────────────────────────────────────────────────────────────────────
-- ENUMS
-- ───────────────────────────────────────────────────────────────────────

create type user_role as enum ('admin', 'closer');

create type lead_tier as enum ('t1', 't2', 't3');

create type lead_status as enum (
    'new',              -- frisch in Queue
    'reviewing',        -- Closer schaut sich Dossier an
    'contacted',        -- Erstkontakt versucht
    'in_conversation',  -- Gespräch laufend
    'meeting_set',      -- Termin/Folgegespräch
    'closed_won',       -- Deal!
    'closed_lost',      -- nicht zustande gekommen
    'do_not_contact'    -- explizit DSGVO-Opt-Out
);

create type bekanntmachung_type as enum (
    'gf_change',           -- Geschäftsführer-Wechsel
    'shareholder_change',  -- Anteilseigner-Änderung
    'new_registration',    -- Neueintragung (Holding-Indikator)
    'capital_increase',    -- Kapital-Erhöhung
    'other'
);

create type activity_type as enum (
    'status_change',
    'note_added',
    'call_attempted',
    'call_completed',
    'email_sent',
    'meeting_scheduled',
    'document_sent',
    'assigned',
    'reassigned'
);

-- ───────────────────────────────────────────────────────────────────────
-- USERS — App-Profile (Supabase Auth speichert E-Mail/Passwort, hier nur App-Daten)
-- ───────────────────────────────────────────────────────────────────────

create table profiles (
    id           uuid primary key references auth.users on delete cascade,
    email        text unique not null,
    role         user_role not null default 'closer',
    full_name    text,
    avatar_url   text,
    last_seen_at timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index profiles_role_idx on profiles (role);

-- ───────────────────────────────────────────────────────────────────────
-- BEKANNTMACHUNGEN_RAW — Roh-Crawl-Daten (immutable, Audit-Quelle)
-- ───────────────────────────────────────────────────────────────────────

create table bekanntmachungen_raw (
    id                    uuid primary key default uuid_generate_v4(),
    source                text not null,           -- 'handelsregister.de' / 'bundesanzeiger.de'
    bekanntmachung_type   bekanntmachung_type not null,
    hrb_nummer            text,
    register_court        text,                    -- 'Hamburg', 'München' etc.
    company_name          text not null,
    company_legal_form    text,                    -- 'GmbH', 'AG', 'UG' ...
    company_address       text,
    company_postal_code   text,
    company_city          text,
    country_code          text not null default 'DE',  -- DE/AT/CH
    bekanntmachung_date   date not null,
    raw_html              text,                    -- Audit-Trail
    raw_text              text,                    -- extrahiert
    parsed_payload        jsonb not null,          -- structured: GF-Name, alte/neue Anteilseigner etc.
    crawl_run_id          uuid not null,           -- gruppiert alle Funde eines Runs
    crawled_at            timestamptz not null default now(),
    -- Dedup-Key
    unique (hrb_nummer, bekanntmachung_date, bekanntmachung_type)
);

create index bek_raw_date_idx on bekanntmachungen_raw (bekanntmachung_date desc);
create index bek_raw_company_idx on bekanntmachungen_raw using gin (company_name gin_trgm_ops);
create index bek_raw_run_idx on bekanntmachungen_raw (crawl_run_id);

-- ───────────────────────────────────────────────────────────────────────
-- COMPANIES — angereicherte Firmen-Stammdaten (1 pro HRB)
-- ───────────────────────────────────────────────────────────────────────

create table companies (
    id                uuid primary key default uuid_generate_v4(),
    hrb_nummer        text unique,
    register_court    text,
    legal_form        text,
    name              text not null,
    address           text,
    postal_code       text,
    city              text,
    country_code      text not null default 'DE',
    -- Bundesanzeiger-Anreicherung
    last_ja_year      int,                    -- Jahresabschluss-Jahr
    equity_eur        numeric(15,2),          -- Eigenkapital
    balance_sum_eur   numeric(15,2),
    ja_fetched_at     timestamptz,
    -- Soft-signals
    has_holding_in_name      boolean default false,
    has_vermoegen_in_name    boolean default false,
    has_family_office_hint   boolean default false,
    has_us_business_hint     boolean default false,
    website           text,
    phone             text,
    impressum_url     text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index companies_hrb_idx on companies (hrb_nummer);
create index companies_name_trgm_idx on companies using gin (name gin_trgm_ops);
create index companies_equity_idx on companies (equity_eur desc nulls last);
create index companies_postal_idx on companies (postal_code);

-- ───────────────────────────────────────────────────────────────────────
-- LEADS — kuratierte Leads (Scoring + Status)
-- ───────────────────────────────────────────────────────────────────────

create table leads (
    id                 uuid primary key default uuid_generate_v4(),
    -- Bezug auf Quelle
    bekanntmachung_id  uuid references bekanntmachungen_raw on delete restrict,
    company_id         uuid references companies on delete restrict,
    -- Person (im Eintrag genannt)
    person_first_name  text,
    person_last_name   text not null,
    person_role        text,                   -- 'Geschäftsführer', 'Gesellschafter' etc.
    person_appointed_at date,                  -- Datum der Bestellung lt. HR
    -- Kontakt
    phone              text,
    phone_source       text,                   -- 'firmen-impressum', 'hr-eintrag', 'manual'
    email              text,
    -- Trigger-Metadata
    trigger_type       bekanntmachung_type not null,
    trigger_date       date not null,
    trigger_summary    text not null,
    -- trigger_freshness_days wird via View berechnet (siehe leads_view weiter unten),
    -- weil generated-column mit current_date nicht IMMUTABLE wäre.
    -- Scoring
    posterior_score    numeric(8,5) not null,  -- 0..1
    tier               lead_tier not null,
    score_breakdown    jsonb not null,         -- {prior, lrs: {name: value}, posterior}
    -- Workflow
    status             lead_status not null default 'new',
    assigned_to        uuid references profiles (id) on delete set null,
    assigned_at        timestamptz,
    best_call_window   text,                   -- 'Di/Mi 10-12 oder 14:30-16'
    -- Dossier
    dossier_markdown   text not null,
    hook_text          text not null,
    objection_handles  jsonb not null,         -- [{objection, response_keyword}, ...]
    -- T1-GOLD Premium-Label (Phase 6.1)
    is_gold            boolean not null default false,
    gold_reason        text,
    -- DSGVO / Lifecycle
    do_not_contact     boolean not null default false,
    do_not_contact_reason text,
    deleted_at         timestamptz,            -- soft-delete
    -- timestamps
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create index leads_tier_idx on leads (tier);
create index leads_status_idx on leads (status);
create index leads_score_idx on leads (posterior_score desc);
create index leads_assigned_idx on leads (assigned_to) where assigned_to is not null;
create index leads_trigger_date_idx on leads (trigger_date desc);
create index leads_created_idx on leads (created_at desc);
create index leads_deleted_idx on leads (deleted_at) where deleted_at is null;
create index leads_gold_idx on leads (is_gold) where is_gold = true;
-- Volltext-Suche
create index leads_search_idx on leads using gin (
    (coalesce(person_last_name, '') || ' ' || coalesce(person_first_name, '')) gin_trgm_ops
);

-- ───────────────────────────────────────────────────────────────────────
-- VIEW: leads mit dynamischem trigger_freshness_days
-- security_invoker=true → RLS-Policies der `leads`-Tabelle greifen.
-- (Workaround weil STORED generated column mit current_date nicht IMMUTABLE wäre)
-- ───────────────────────────────────────────────────────────────────────

create or replace view leads_view
with (security_invoker = true)
as
select
    l.*,
    (current_date - l.trigger_date)::int as trigger_freshness_days
from leads l;

-- ───────────────────────────────────────────────────────────────────────
-- LEAD_ASSIGNMENTS — Zuweisungs-Historie (Audit + Multi-Closer-Conflict-Prevention)
-- ───────────────────────────────────────────────────────────────────────

create table lead_assignments (
    id           uuid primary key default uuid_generate_v4(),
    lead_id      uuid not null references leads on delete cascade,
    user_id      uuid not null references profiles (id) on delete cascade,
    assigned_by  uuid references profiles (id),
    assigned_at  timestamptz not null default now(),
    released_at  timestamptz,                  -- null = aktiv
    notes        text
);

create index lead_assignments_lead_idx on lead_assignments (lead_id) where released_at is null;
create index lead_assignments_user_idx on lead_assignments (user_id) where released_at is null;
-- Exklusiv-Lock: ein Lead darf zu einem Zeitpunkt nur einem Closer aktiv zugewiesen sein
create unique index lead_assignments_active_unique on lead_assignments (lead_id) where released_at is null;

-- ───────────────────────────────────────────────────────────────────────
-- LEAD_ACTIVITIES — Aktivitäts-Timeline pro Lead
-- ───────────────────────────────────────────────────────────────────────

create table lead_activities (
    id          uuid primary key default uuid_generate_v4(),
    lead_id     uuid not null references leads on delete cascade,
    user_id     uuid not null references profiles (id) on delete restrict,
    activity_type activity_type not null,
    payload     jsonb,                          -- z.B. {old_status, new_status} oder {note_md}
    note_md     text,                           -- markdown
    created_at  timestamptz not null default now()
);

create index activities_lead_idx on lead_activities (lead_id, created_at desc);
create index activities_user_idx on lead_activities (user_id, created_at desc);

-- ───────────────────────────────────────────────────────────────────────
-- AUDIT_LOG — Security-relevante Actions (Login, Lead-View, Export)
-- ───────────────────────────────────────────────────────────────────────

create table audit_log (
    id          uuid primary key default uuid_generate_v4(),
    user_id     uuid references profiles (id),
    action      text not null,                -- 'login', 'lead.view', 'lead.export.pdf', 'lead.delete'
    resource_type text,                       -- 'lead', 'company', ...
    resource_id text,                         -- string-id für Flexibilität
    ip_address  inet,
    user_agent  text,
    payload     jsonb,
    created_at  timestamptz not null default now()
);

create index audit_user_idx on audit_log (user_id, created_at desc);
create index audit_action_idx on audit_log (action, created_at desc);
create index audit_resource_idx on audit_log (resource_type, resource_id);

-- ───────────────────────────────────────────────────────────────────────
-- CRAWL_RUNS — Pipeline-Telemetrie (Frühwarn-Signale aus Pre-Mortem)
-- ───────────────────────────────────────────────────────────────────────

create table crawl_runs (
    id              uuid primary key default uuid_generate_v4(),
    started_at      timestamptz not null default now(),
    finished_at     timestamptz,
    status          text not null default 'running',  -- 'running' | 'success' | 'failed' | 'captcha'
    pages_fetched   int default 0,
    captchas_hit    int default 0,
    bekanntmachungen_found int default 0,
    leads_created   int default 0,
    error_message   text,
    notes           text
);

create index crawl_runs_started_idx on crawl_runs (started_at desc);

-- ───────────────────────────────────────────────────────────────────────
-- TRIGGER: updated_at automatisch
-- ───────────────────────────────────────────────────────────────────────

create or replace function tg_set_updated_at()
returns trigger as $$
begin
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;

create trigger profiles_updated before update on profiles
    for each row execute function tg_set_updated_at();
create trigger companies_updated before update on companies
    for each row execute function tg_set_updated_at();
create trigger leads_updated before update on leads
    for each row execute function tg_set_updated_at();

-- ───────────────────────────────────────────────────────────────────────
-- ROW LEVEL SECURITY
-- ───────────────────────────────────────────────────────────────────────

alter table profiles            enable row level security;
alter table companies           enable row level security;
alter table bekanntmachungen_raw enable row level security;
alter table leads               enable row level security;
alter table lead_assignments    enable row level security;
alter table lead_activities     enable row level security;
alter table audit_log           enable row level security;
alter table crawl_runs          enable row level security;

-- Helper: ist current user admin?
create or replace function is_admin()
returns boolean as $$
    select coalesce((
        select role = 'admin' from profiles where id = auth.uid()
    ), false);
$$ language sql stable security definer;

-- Helper: hat current user den Lead zugewiesen?
create or replace function has_lead_assignment(p_lead_id uuid)
returns boolean as $$
    select exists (
        select 1 from lead_assignments
        where lead_id = p_lead_id
          and user_id = auth.uid()
          and released_at is null
    );
$$ language sql stable security definer;

-- ─── PROFILES ─────────────────────────────────────────
create policy profiles_self_read on profiles
    for select using (id = auth.uid() or is_admin());
create policy profiles_self_update on profiles
    for update using (id = auth.uid());
create policy profiles_admin_all on profiles
    for all using (is_admin());

-- ─── COMPANIES (Stammdaten — alle authenticated dürfen lesen) ─────────────
create policy companies_authenticated_read on companies
    for select using (auth.uid() is not null);
create policy companies_admin_write on companies
    for all using (is_admin());

-- ─── BEKANNTMACHUNGEN_RAW (nur Admin) ─────────────────────────────────────
create policy bek_raw_admin_only on bekanntmachungen_raw
    for all using (is_admin());

-- ─── LEADS — Kern-Policy ──────────────────────────────────────────────────
-- Admin: alles
create policy leads_admin_all on leads
    for all using (is_admin());

-- Closer: nur Leads die ihm zugewiesen sind
create policy leads_closer_assigned_read on leads
    for select using (
        not is_admin()
        and has_lead_assignment(id)
        and deleted_at is null
    );

create policy leads_closer_assigned_update on leads
    for update using (
        not is_admin()
        and has_lead_assignment(id)
        and deleted_at is null
    )
    with check (
        not is_admin()
        and has_lead_assignment(id)
        -- Closer darf KEINE Felder ändern ausser Status/best_call_window/dossier-Notizen
        -- Enforcement via Server-Action whitelist (DB ist letzte Verteidigungslinie)
    );

-- ─── LEAD_ASSIGNMENTS ─────────────────────────────────────────────────────
create policy assignments_admin_all on lead_assignments
    for all using (is_admin());

create policy assignments_self_read on lead_assignments
    for select using (user_id = auth.uid());

-- ─── LEAD_ACTIVITIES ──────────────────────────────────────────────────────
create policy activities_admin_all on lead_activities
    for all using (is_admin());

create policy activities_closer_read_assigned on lead_activities
    for select using (
        not is_admin()
        and has_lead_assignment(lead_id)
    );

create policy activities_closer_insert_assigned on lead_activities
    for insert with check (
        user_id = auth.uid()
        and (is_admin() or has_lead_assignment(lead_id))
    );

-- ─── AUDIT_LOG (nur Admin lesen, alle authenticated schreiben) ──────────
create policy audit_admin_read on audit_log
    for select using (is_admin());

create policy audit_authenticated_insert on audit_log
    for insert with check (auth.uid() is not null);

-- ─── CRAWL_RUNS (nur Admin) ───────────────────────────────────────────────
create policy crawl_runs_admin_only on crawl_runs
    for all using (is_admin());

-- ───────────────────────────────────────────────────────────────────────
-- GRANTS — Supabase-Service-Roles brauchen explizite Permissions
-- (RLS-Policies regeln dann WAS pro Rolle sichtbar ist)
-- ───────────────────────────────────────────────────────────────────────

grant usage on schema public to anon, authenticated, service_role;

grant select, insert, update, delete on all tables in schema public to service_role;
grant select, insert, update on all tables in schema public to authenticated;
grant select on all tables in schema public to anon;

-- Sequenzen für inserts
grant usage, select on all sequences in schema public to service_role, authenticated;

-- Zukünftige Tabellen automatisch grants vergeben
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;
alter default privileges in schema public grant select, insert, update on tables to authenticated;
alter default privileges in schema public grant select on tables to anon;
alter default privileges in schema public grant usage, select on sequences to service_role, authenticated;

-- ───────────────────────────────────────────────────────────────────────
-- INITIAL DATA — bei Bedarf manuell oder via Seed-Script
-- ───────────────────────────────────────────────────────────────────────

-- (nichts hier hardcoded — Admin-User wird via Supabase-Dashboard erstellt)

-- ═══════════════════════════════════════════════════════════════════════
-- END OF SCHEMA
-- ═══════════════════════════════════════════════════════════════════════
