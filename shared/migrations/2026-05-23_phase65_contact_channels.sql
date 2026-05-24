-- Phase 6.5: Multi-Channel-Dossier + F-Pack-Felder
-- In Supabase ausführen: SQL Editor → New Query → Paste → Run.

-- 1) Multi-Channel-Kontakt-Array in leads
alter table leads
    add column if not exists contact_channels jsonb not null default '[]'::jsonb;

create index if not exists leads_contact_channels_gin
    on leads using gin (contact_channels);

-- 2) Erweiterte BA-Enrichment-Felder in companies (sofern vorhanden)
-- (Falls die Tabelle den equity_eur/balance_sum_eur-Block nicht hat, ignorieren.)
do $$
begin
    if exists (select 1 from information_schema.tables where table_name='companies') then
        execute 'alter table companies add column if not exists liquid_assets_eur numeric';
        execute 'alter table companies add column if not exists operating_cashflow_eur numeric';
        execute 'alter table companies add column if not exists profit_eur numeric';
        execute 'alter table companies add column if not exists has_paragraph_match boolean default false';
        execute 'alter table companies add column if not exists paragraph_matches jsonb default ''[]''::jsonb';
        execute 'alter table companies add column if not exists wphg_voting_rights_count int';
        execute 'alter table companies add column if not exists wphg_companies jsonb default ''[]''::jsonb';
    end if;
end$$;

-- 3) Hinweis: leads_view neu erstellen (wenn die View existiert und Spalten projiziert)
-- Wir brauchen die View nicht zu ändern wenn sie select * benutzt — Postgres
-- ergänzt neue Spalten automatisch beim nächsten View-Recreate.
