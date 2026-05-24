# OPERATIONS — Tägliche Nutzung & Wartung

> Wie du das System täglich nutzt + was bei Problemen tun.

---

## Täglich (Admin / Lead-Lieferant)

### Morgens (5 Min)
1. **Vercel-URL öffnen** (oder lokal `localhost:3001`)
2. Magic-Link → Login (falls Session abgelaufen)
3. **Dashboard checken:**
   - Wie viele neue T1-Leads über Nacht?
   - Captcha-Hit-Rate ok? (`/runs`)
   - Closer-Activity letzte 48h?
4. **Top-Leads-Liste durchgehen**
   - Anti-Persona-Hinweise im Hook erkennbar? → DnC setzen
   - Identity verifizierbar? → Closer zuweisen
5. **Closer-Briefing per WhatsApp/Mail** mit ~3-5 frischen Lead-IDs

### Abends (5 Min)
1. **Activity-Timeline pro Top-Lead checken** — wer hat was gemacht?
2. **Status-Stand**: was ist von "contacted" → "in_conversation" / "meeting_set"?
3. **Notizen lesen** — was haben Closer gehört?

---

## Wöchentlich (Sonntag, 20 Min)

1. **Pipeline-Tier-Verteilung** über 7 Tage anschauen
   - T1-Rate kalibrierungs-tauglich? (~5-10% von Bekanntmachungen)
   - Falls T1 zu wenige: LR in `pipeline/helium_pipeline/scoring/bayes.py` justieren
2. **Closing-Rate**: wie viele `closed_won` vs `closed_lost`?
3. **Captcha-Trend**: steigt die Captcha-Hit-Rate?
4. **Konkurrenz-Watch**: Resch-Anwälte / NASCO-Newsfeed checken

---

## Wenn die Pipeline läuft (GitHub Actions)

Daily Cron: **05:00 UTC** (= 07:00 Berlin Sommer, 06:00 Berlin Winter)

### Logs anschauen
- `github.com/Ibrahimfarajk/Helium-prospector/actions` → "Daily Lead Pipeline"
- Latest Run → Artifacts → `pipeline-run-XXXXX.zip` enthält `run_summary_*.json`

### Manueller Run
- Actions-Tab → "Daily Lead Pipeline" → "Run workflow" Button → `days_back=3, max_pages=5`

### Live-Crawler ist noch TODO Phase 4
- Pipeline läuft aktuell mit Mock-Source (siehe BUILD_LOG.md Phase 2)
- Echter handelsregister.de-Crawler braucht noch Cookie-Banner-Akzept-Flow
- Workaround bis dahin: wöchentlich manueller HR-Bekanntmachungen-Scrape, JSON in DB importieren

---

## Pre-Mortem-Frühwarn-Signale

Check im Dashboard / `/runs`:

| Signal | Threshold | Aktion |
|---|---|---|
| Captcha-Hit-Rate >20% | warning | Stealth-Settings überprüfen |
| Captcha-Hit-Rate >40% | alert | Pipeline pausieren, manuell crawlen |
| Keine Closer-Logins seit 48h | warning | Closer anpingen |
| Keine Closer-Logins seit 7T | alert | Closer-Onboarding wiederholen |
| T1-Conversion-Rate <5% | warning | Bayes-LR neu kalibrieren |
| DnC-Rate letzte 30T >5% | alert | Closer-Diskretion thematisieren |

---

## Closer-Onboarding

### Neuen Closer hinzufügen
1. Supabase-Dashboard → Authentication → Users → Add User
2. Email + Confirm
3. SQL Editor:
   ```sql
   insert into profiles (id, email, role, full_name)
   values ('<USER-ID>', '<email>', 'closer', '<Name>');
   ```
4. (Optional) Lead zuweisen:
   ```sql
   insert into lead_assignments (lead_id, user_id, assigned_by)
   values ('<lead-id>', '<closer-id>', '<deine-admin-id>');
   ```

### Closer kann sehen:
- Nur Leads die ihm explizit zugewiesen sind (lead_assignments)
- Aktivitäten + Notizen seiner Leads
- Nicht: andere Leads, Audit-Log, Crawl-Telemetrie

---

## Datenmodell-Übersicht (für Notfälle)

```sql
-- Lead-Liste mit Frische
select tier, person_last_name, posterior_score, trigger_freshness_days, status
from leads_view
where deleted_at is null
order by posterior_score desc;

-- Closer-Activity
select p.email, count(*) as actions, max(la.created_at) as last_action
from lead_activities la
join profiles p on p.id = la.user_id
where la.created_at > now() - interval '7 days'
group by p.email;

-- Pre-Mortem-Health
select status, count(*) from crawl_runs
where started_at > now() - interval '7 days'
group by status;
```

---

## Notfall: System läuft nicht

| Symptom | Check |
|---|---|
| Vercel-URL 500-Error | Vercel-Logs (vercel.com/dashboard/[project]/logs) — meist env-var missing |
| Magic-Link kommt nicht | Supabase Auth-Logs → Rate-Limit? Spam-Ordner? Free-Tier-SMTP-Throttle |
| Dashboard ist leer | `select count(*) from leads` — leer? Pipeline lief nicht. |
| "permission denied" Errors | SQL Editor: `grant select on <table> to authenticated, service_role;` neu vergeben |
| GitHub Actions fail | Actions-Tab → Logs → meist Secret fehlt oder Playwright-Install-Issue |

---

## Backup

Supabase Free-Tier hat 7 Tage automatische daily backups. Restore via Dashboard.

Manuell:
```bash
pg_dump postgresql://postgres:<PW>@db.jkqgpfbnplthchifwhqy.supabase.co:5432/postgres \
  -t leads -t lead_activities -t profiles \
  > backup-$(date +%Y%m%d).sql
```

---

## Skalierung (wenn die ersten Provisions reinkommen)

- **Vercel Hobby → Pro** (20$/Monat): kommerzielle Nutzung erlaubt, höhere Limits
- **Supabase Free → Pro** (25$/Monat): 8 GB DB, 100 GB Bandbreite, kein 7-Tage-Pause
- **Eigene Domain** (~10€/Jahr)
- **Northdata-Pro** (ab dem ersten Deal): 200€/Monat aber dramatisch bessere Datenqualität

Total nach Skalierung: ~60-300€/Monat. Bei 5.700 EUR/Deal Break-Even bei 1 Deal/Monat.
