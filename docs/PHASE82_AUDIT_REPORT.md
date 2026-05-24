# Phase 8.2 Pre-Cron-Audit Report

**Datum:** 2026-05-24
**Time-Box:** 60-90 Min — eingehalten
**Tag:** Vor erstem Live-Cron-Run morgen 05:00 UTC

---

## Pflicht-Punkte (User-Vorgabe)

| # | Punkt | Befund | Severity |
|---|---|---|---|
| A | Test-Suite | **207/207 grün** (war 186) — keine Skips, keine Warnings auch mit `-W error` | ✅ |
| B | DB-Schema | 9 Tabellen alle reachable, RLS aktiv, anon korrekt geblockt | ✅ |
| C | Cron-Config | Schedules + Secrets + Permissions OK; **Finding**: keepalive lief 3× — gefixt auf 1× | ✅ gefixt |
| D | End-to-End | Mock-Pipeline läuft sauber, Drift-Snapshot wird berechnet | ✅ |
| E | Error-Handling | CaptchaDetected + HTTPError + DB-Fail alle gracefully | ✅ |
| F | Bayes-Edges | Leer/Maxed/Penalty-Stack alle korrekt | ✅ |
| G | Performance | **87ms / 1000 Leads** — 31% schneller als Phase-7-Baseline (126ms) | ✅ |
| H | Security | **KRITISCHES FINDING — DB-Passwort committed** — gefixt + Password rotiert | ⚠️ gefixt |
| I | Dokumentation | BUILD_LOG aktuell, ADMIN_GUIDE bereinigt | ✅ |
| J | Cron-Trockenübung | Schedule-Match-Logik korrekt, würde durchlaufen | ✅ |

## Ergänzungspunkte (Claude-Vorschläge K-P)

| # | Punkt | Befund | Severity |
|---|---|---|---|
| K | Frontend mit neuen JSONB-Feldern | TS-Build clean, Vercel 200, alte+neue Leads rendern | ✅ |
| L | workflow_dispatch-Mode-Logik | Race-Bedingungen ausgeschlossen | ✅ |
| M | Person-Extraction-Qualität | **13/13 = 100% Coverage** auf existing Leads | ✅ |
| N | Rescore-Pytest | **21 neue Tests** — Property-Tests für Roundtrip-Stabilität | ✅ gebaut |
| O | GitHub-Actions-Quota | Concurrency-Cancel hinzugefügt, ~720 Min/Monat im 2000-Min-Limit | ✅ gefixt |
| P | Drift-FK-Race | Code-Pfad linear: crawl_run insert vor snapshot insert | ✅ kein Issue |

---

## Findings im Detail

### H-1 (KRITISCH, gefixt) — DB-Passwort im git-tracked Markdown

**Vorgefunden:** `UduZGmP7GW6MzhP4` (echtes Supabase-DB-Password) im Klartext in:
- `docs/MORGEN_WEITER.md:54` (von Phase 5)
- `docs/ADMIN_GUIDE.md:214` (von mir in Phase 7 fälschlicherweise reingeschrieben — eigener Fehler)

**Risiko-Bewertung:** Repo ist **private** (verifiziert: 404 ohne Login). Exposure auf:
- alle Repo-Maintainer-Klone
- GitHub-Mitarbeiter mit Code-Access
- Backups falls Repo je geklont wurde

**Mitigation:**
1. ✅ Files cleanen (Commit `087e44f`):
   - `MORGEN_WEITER.md` → generic Hinweis
   - `ADMIN_GUIDE.md` → `<DATABASE_PASSWORD>`-Placeholder
2. ✅ User: Supabase DB-Password Reset durchgeführt
3. ✅ Service-Role-Key in `.env` unverändert (separater JWT) — Cron läuft morgen unbeeinträchtigt
4. ⏸ git-history-Rewrite **bewusst skipped** (private Repo + neues Passwort = altes wertlos)

**Sanity-Check nach Rotation:** Service-Role-Key + Schreib-Probe in drift_snapshots erfolgreich.

### C-1 (Vermutlich, gefixt) — Keepalive-Job feuerte 3× täglich

**Vorgefunden:** `if: github.event_name == 'schedule'` matched alle 3 Schedules.
**Fix:** Filter auf `github.event.schedule == '0 5 * * *'` → läuft nur beim Morning-Cron.
**Impact:** 2/3 Quota-Verschwendung gespart (~10 sek × 2 × 365 = 2 Stunden/Jahr).

### L-1 (Vermutlich, gefixt) — Delta-Fallback verschluckte Errors

**Vorgefunden:** `helium-pipeline rescore … || echo "rescore-Command noch nicht implementiert"` — Erbe aus der Zeit vor rescore-CLI. Jeder echte rescore-Fehler wäre Workflow-grün geblieben.
**Fix:** `|| echo`-Fallback entfernt. Echter Fehler → Workflow rot → Discord-Webhook (wenn `DISCORD_WEBHOOK_URL` Secret gesetzt).

### O-1 (Sicher, mitigiert) — Quota-Marge bei Concurrent Runs

**Vorgefunden:** Free-Tier 2000 Min/Monat. Geschätzt 720 Min/Monat — 64% Marge.
**Fix:** `concurrency: { group: helium-pipeline, cancel-in-progress: true }` — überlappende Runs werden gecancelt statt parallel zu laufen.
**Effekt:** Auch bei hängendem Captcha-Stuck-Run wird der nächste Schedule den alten cancel'n → kein Quota-Burn.

### B-1 (Vermutlich, NICHT gefixt) — drift_snapshots fehlt GRANT

**Vorgefunden:** Anon-Key auf `drift_snapshots` gibt "permission denied" (nicht "0 rows" wie bei anderen Tabellen). Pipeline schreibt mit service_role (bypasst GRANT), also funktional kein Issue.
**Warum nicht gefixt:** Kein operatives Problem. Wenn Frontend mal Drift-Dashboard zeigen will, separate Migration:
```sql
grant select on drift_snapshots to authenticated;
```
**Risk:** None. Phase 8.3 wenn Frontend-Bedarf entsteht.

---

## Was nach Audit committed wurde

| Commit | Inhalt |
|---|---|
| `087e44f` | security: Klartext-Password aus 2 Markdown-Files entfernt |
| folgt | Audit-Fixes: workflow keepalive + delta-fallback + concurrency + Rescore-Tests + dieser Report |

## Tests Stand Audit-Ende

- **207/207 Python-Tests grün** (war 186 vor Audit, +21 Rescore-Property-Tests)
- **TypeScript Web-Build clean**
- **Next.js Production-Build OK** (alle 11 Routes generiert)
- **YAML Workflow-File valide**

## Cron-Plan für morgen (2026-05-25)

```
05:00 UTC (07:00 Berlin) → FULL crawl (handelsregister + bundesanzeiger)
                          → KEEPALIVE-Job parallel
09:00 UTC (11:00 Berlin) → DELTA rescore (30 Top-Leads)
13:00 UTC (15:00 Berlin) → DELTA rescore (30 Top-Leads)
```

Bei jedem Run: Drift-Snapshot in `drift_snapshots`-Tabelle.

## Was du morgen früh prüfen solltest

1. **GitHub Actions → letzter Run grün?**
   - `crawl`-Job status
   - Bei rot → Logs öffnen, Discord-Alert (wenn Webhook gesetzt)
2. **Supabase → `crawl_runs`-Tabelle**: 1 neuer Row mit `status=success`?
3. **Supabase → `drift_snapshots`**: mindestens 1 neuer Row mit `posterior_mean`?
4. **App → `/leads`**: neue Leads sichtbar? Tier-Verteilung sinnvoll?
5. **Optional manuell**: `helium-pipeline rescore --limit 5 --dry-run` lokal — vergleiche mit DB-State.

## Was nicht in Phase 8.2 reingehört (echte 8.3-Punkte)

- B-1: GRANT für drift_snapshots authenticated (wenn Frontend-Bedarf)
- Frontend-UI für `family_breakdown` + `reachability.confidence_stars`
- Discord-Drift-Alert scharfschalten (nach 7d Real-Daten)
- Bayes-Re-Kalibrierung nach Closer-Feedback
- B3-Liste ausbauen (~200 Einträge statt 50, sobald Real-Daten Coverage-Lücken zeigen)

---

**Audit abgeschlossen. System ready für Cron morgen.**
