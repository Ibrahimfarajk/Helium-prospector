# Admin-Anleitung — helium-prospector

Für **Ibrahim**. Dieses Doc ist die operative Bibel.

---

## 1. System-URLs

| Komponente | URL |
|---|---|
| Production-App | https://helium-prospector.vercel.app |
| Supabase-Console | https://supabase.com/dashboard/project/jkqgpfbnplthchifwhqy |
| GitHub-Repo | https://github.com/Ibrahimfarajk/Helium-prospector |
| GitHub Actions | https://github.com/Ibrahimfarajk/Helium-prospector/actions |
| Vercel-Dashboard | https://vercel.com/ibrahims-projects |

---

## 2. Daily-Health-Check (5 min, jeden Morgen)

```
Schritt 1: GitHub Actions → letzter "Daily Lead Pipeline"-Run
  - Status grün? ✅
  - Status rot? → Logs öffnen, fehlerhafte Stage identifizieren

Schritt 2: App öffnen → Dashboard
  - Wieviele neue Leads heute?
  - Top-Lead Posterior sinnvoll (10-40%)?
  - GOLD-Anteil ~5-15%?

Schritt 3: Supabase → Tabelle "crawl_runs"
  - Letzter Eintrag <24h?
  - pages_fetched > 0?
  - captchas_hit == 0?
```

---

## 3. Closer-Account anlegen

**Via Supabase SQL-Editor:**

```sql
-- 1. User per Magic-Link einladen (in Supabase Auth-Tab)
-- 2. Sobald er sich eingeloggt hat:
update profiles
  set role = 'closer'
  where email = 'closer-email@example.com';
```

**Lead-Zuweisung:**

```sql
insert into lead_assignments (lead_id, user_id, assigned_by)
select l.id, p.id, '<dein-admin-uuid>'
from leads l, profiles p
where p.email = 'closer-email@example.com'
  and l.tier = 't1'
  and l.assigned_to is null
limit 10;
```

---

## 4. Watch-Liste pflegen

Datei: `shared/helium_watch.json`

```json
{
  "entries": [
    {
      "name": "Mustermann Helium GmbH",
      "name_normalized": "mustermann helium",
      "hrb_nummer": "HRB 12345",
      "category": "helium_industry",
      "anti_persona": false,
      "notes": "Großkunde, hatte vor 2 Jahren angefragt"
    }
  ]
}
```

`anti_persona: true` heißt: dieser Lead wird vom Score-Pipeline **ausgeschlossen** (Konkurrenz, Issuer, problematische Persona).

Nach Editierung:
```bash
git add shared/helium_watch.json
git commit -m "watch-list: add Mustermann"
git push
# wirkt sich beim nächsten Daily-Cron aus
```

---

## 5. BaFin-Vermittler-Liste pflegen

Datei: `shared/bafin_vermittler.json` — alle Vermittler-Konkurrenten die ausgeschlossen werden sollen.

Quelle: https://www.bafin.de → Vermittlerregister.

```json
{
  "name": "Konkurrenz GmbH",
  "name_normalized": "konkurrenz",
  "bafin_id": "80175797",
  "category": "sachwert_vermittler",
  "anti_persona": true,
  "notes": "Vermittelt gleiche Asset-Klasse"
}
```

---

## 6. Manueller Pipeline-Run

```
GitHub → Actions → "Daily Lead Pipeline" → Run workflow
Optional:
  - max_pages: 3 (default) | erhöhen bei Backlog
  - days_back: 1 (default) | erhöhen für Backfill
```

**WICHTIG:** Mehr als 5 manuelle Runs/Stunde → IP-Ban-Risiko bei handelsregister.de.

---

## 7. Datenbank manuell prüfen / korrigieren

```sql
-- Top-10 Posterior-Leads
select id, person_last_name, posterior_score, tier, is_gold, status
from leads
where deleted_at is null
order by posterior_score desc
limit 10;

-- Lead manuell zu T1 zwingen (z.B. nach Closer-Feedback)
update leads set tier = 't1', is_gold = true, gold_reason = 'manual_override'
where id = '<uuid>';

-- Lead soft-löschen (kommt aus Closer-View raus, bleibt für Audit)
update leads set deleted_at = now() where id = '<uuid>';

-- Audit-Log durchsuchen
select created_at, action, resource_id, payload
from audit_log
order by created_at desc
limit 50;
```

---

## 8. Performance-Tuning

### Bayes-Schwellen (in `pipeline/helium_pipeline/scoring/bayes.py`)

```python
T1_THRESHOLD = 0.15  # höher = weniger Top-Leads
T2_THRESHOLD = 0.05
T3_THRESHOLD = 0.01  # alles drunter wird verworfen

EK_MIN = 500_000.0   # Vermögens-Gate
```

Empfehlung: nach 2 Wochen Closer-Feedback anpassen, nicht früher.

### Likelihood-Ratios

Tabelle in `bayes.py:LR_TABLE`. Wenn z.B. "GF-Wechsel" zu oft fälschlich Tier-1 ist:

```python
"trigger_gf_change": 6.0  →  4.0
```

Senkt den Boost für diese Trigger-Klasse.

---

## 9. Backfill bestehender Leads

Wenn neue Felder/Schema-Migration:

```bash
cd pipeline
python scripts/backfill_contact_channels.py   # idempotent
```

Schreibt nur in Leads die das Feld leer haben.

---

## 10. Crawler-Stop-Notfall

Wenn IP gesperrt wird (HTTP 429/403 in Logs):

```
GitHub → Actions → Daily Lead Pipeline → "Disable workflow"
ODER: shared/db_schema.sql temporär patchen mit insert-Trigger der ablehnt
```

Wieder enabling nach Cool-Down 24-48h.

---

## 11. Backup

Supabase macht **automatisches Daily-Backup** (Free-Tier behält 7 Tage). Für längere Aufbewahrung:

```bash
pg_dump $DATABASE_URL > backup-$(date +%F).sql
```

DATABASE_URL Format: `postgres://postgres:UduZGmP7GW6MzhP4@db.jkqgpfbnplthchifwhqy.supabase.co:5432/postgres`

---

## 12. Phase-7-Audit-Findings

Siehe [`PHASE7_AUDIT_REPORT.md`](PHASE7_AUDIT_REPORT.md).

Wichtigste offene Punkte:
- ⏳ Sentry/Error-Tracking
- ⏳ Rate-Limiting auf Server-Actions
- ⏳ Closer-Update-Policy-Whitelist (RLS Spalten-Schutz)
- ⏳ UX-Verbesserungen P0/P1 aus [`PHASE7_AUDIT_REPORT.md`](PHASE7_AUDIT_REPORT.md)

---

## 13. Eskalations-Kontakte

- **Vercel-Issues:** Dashboard → Support
- **Supabase-Issues:** Discord-Community (sehr schnell)
- **DNS/Domain:** Vercel default-Domain reicht für jetzt
- **Anwalt für DSGVO-Fragen:** schon eingeholt, separater Track
