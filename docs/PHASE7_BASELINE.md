# Phase 7 Baseline — pre-audit snapshot

**Datum:** 2026-05-24 14:20 UTC
**Tag:** `pre-phase7-audit`
**Commit:** `1bd0421` — "Phase 6.5 F-Pack + Multi-Channel-Dossier"

## Production-Status

| Komponente | Status | Beleg |
|---|---|---|
| Vercel Deploy | ✅ Live | `HTTP 307 → /login` (Auth-Redirect funktioniert) |
| Server: Vercel (fra1) | ✅ | `X-Vercel-Id: fra1::jhvmb-...` |
| HTTPS/HSTS | ✅ | `Strict-Transport-Security: max-age=63072000; preload` |
| Supabase DB-Migration | ✅ Live | User-Bestätigung: heute 16:00 SQL-Editor `Success. No rows returned` |
| GitHub Actions Secrets | ✅ | SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY gesetzt |
| Daily-Cron | ⏳ Noch nicht gelaufen | Erste Ausführung 2026-05-25 05:00 UTC |

## Test-Baseline

**101/101 Tests grün** (Pipeline, 0.83s):

```
tests/test_affinity.py            22
tests/test_anti_filters.py        29
tests/test_block2_filters.py      10
tests/test_contact_channels.py     7
tests/test_f_pack.py              21
tests/test_*  (rest)              12
```

## Rollback-Plan

```bash
# Falls Phase 7 etwas bricht:
git reset --hard pre-phase7-audit
git push --force-with-lease  # nur nach explizitem User-OK
```

## Phase-7-Reihenfolge (vereinbart)

```
1 → 9 (Health) → 6 (RLS-Pre-Check) → 2 (Backfill) →
3+5+8 (Bug+Quality+a11y) → 4 (Perf) →
7+10 (UX+Docs) → 11 (Live-Trigger)
```
