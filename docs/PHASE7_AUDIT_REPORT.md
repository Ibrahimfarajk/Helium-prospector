# Phase 7 Audit Report

**Start:** 2026-05-24 14:20 UTC
**Tag:** `pre-phase7-audit` → Commit `1bd0421`
**Tests vor Start:** 101/101 grün

---

## Box 9 — Production-Health-Check ✅

### Live-Status

| Komponente | Status | Latenz |
|---|---|---|
| Vercel `/` | ✅ 307 → /login | 144ms (fra1) |
| Vercel `/login` | ✅ 200 OK | < 200ms |
| Vercel `/leads` | ✅ 307 → /login (Auth-Guard wirkt) | — |
| HTTPS/HSTS | ✅ `max-age=63072000; preload` | — |
| Supabase URL | ✅ `jkqgpfbnplthchifwhqy.supabase.co` | < 500ms |
| Daily-Cron | ✅ konfiguriert `0 5 * * *` UTC | wartet auf erste Ausführung |
| Keep-Alive-Job | ✅ aktiv (verhindert Supabase-Pause) | — |

### Tabellen-Inhalte

```
profiles              : 5 rows    (Closer/Admin Accounts)
companies             : 0 rows    (optional Enrichment, wird via Pipeline gefüllt)
leads                 : 13 rows   (alle ohne contact_channels → Backfill in Box 2)
bekanntmachungen_raw  : 30 rows
crawl_runs            : 2 rows    (Test-Läufe Phase 5)
```

### Findings

- `contact_channels`-Migration ist live in Supabase, alle 13 Leads haben `[]`. **Backfill nötig → Box 2.**
- Keine `companies`-Rows angelegt; ist erwartet (Enrichment ist optional pro Lead).
- `robots.txt` liefert 404 — minor, kein Prio-Issue.
- Kein Sentry / kein zentrales Error-Tracking — auf TODO-Liste für Phase 8.
- Discord-Webhook-Secret optional, derzeit unklar ob User es gesetzt hat.

### Box 9 — keine Code-Änderungen, nur Audit. ✅

---

## Box 6 — Security & RLS-Audit ✅

### RLS Verifikation (live gegen Supabase)

| Test | Erwartet | Ergebnis |
|---|---|---|
| Anon-Key → `leads` | 0 sichtbar | ✅ 0 (von 13 in DB) |
| Anon-Key → `profiles` | 0 sichtbar | ✅ 0 (von 5 in DB) |
| Anon-Key → `audit_log` | 0 sichtbar | ✅ 0 (von 1 in DB) |
| Service-Role → alle 8 Tabellen | voll sichtbar | ✅ (Pipeline + Cron) |

**RLS aktiv auf:** profiles, companies, bekanntmachungen_raw, leads, lead_assignments, lead_activities, audit_log, crawl_runs.

### Server-Actions

Alle 4 Server-Actions (`updateLeadStatus`, `addNote`, `rateLead`, `markDoNotContact`) prüfen
`supabase.auth.getUser()` und werfen `not_authenticated` bei fehlendem User. RLS ist die zweite Verteidigungsschicht (Closer sieht nur assigned leads).

### Secret-Scan

- `.env`, `.env.local`, `.env.*.local`, `*.pem`, `*.key` sind alle gitignored.
- `git grep` über Codebase findet keine committed Keys/Passwords.
- Service-Role-Key liegt nur in `pipeline/.env` und `web/.env.local` (beide gitignored), zusätzlich als GitHub-Actions-Secret.

### Console-Logging

- Genau 1 console-call in Production-Code: `web/src/lib/db/queries.ts:console.error("fetchLeads failed", error)` — kein sensitives Datum, nur Error-Object.

### Fixes in Box 6

- **Input-Length-Limits** auf `addNote` (5000 Zeichen) und `markDoNotContact.reason` (500 Zeichen) — DOS-Schutz gegen riesige JSONB-Inserts.

### Bekannte Einschränkungen (NICHT gefixt, gelistet)

- ⚠️ **Closer-Update-Policy** auf `leads`: WITH CHECK enforced nur "is assigned", nicht "nur diese Felder darf der Closer ändern". Server-Action ist der Schutz. Wenn jemand direkt mit dem User-Token auf Supabase zugreift, könnte er theoretisch andere Spalten updaten. **Mitigation für Phase 8:** Spalten-Whitelist via Trigger ODER Spalten-spezifische Policy.
- ⚠️ **Kein Rate-Limiting** auf Server-Actions oder API-Routes (`/api/keepalive`). Bei Brute-Force / Spam-Submit kein Throttle. Vercel hat IP-basiertes Edge-Limiting (kostenlos), aber explizite Limits fehlen.
- ⚠️ **Kein Sentry / kein Error-Tracking** — Server-Action-Errors gehen in Vercel-Logs, sind aber schwer zu durchsuchen.

---

## Box 2 — Backfill 13 Leads ✅

Script: `pipeline/scripts/backfill_contact_channels.py` (idempotent).

### Ergebnis

| Status | Anzahl |
|---|---|
| Mit `contact_channels` befüllt | **11** |
| Kein legacy-Phone/Email, leer gelassen | 2 |
| Total | 13 |

- Mobile/Phone unterschieden über Regex `01[567]...` (0.75 vs 0.7 confidence).
- Generic-Inboxen (`info@`, `kontakt@`, …) bekommen 0.5 statt 0.7 (User kann später überschreiben).
- `source = "legacy_migration"` für saubere Audit-Trail.
- Die 2 Leads ohne Daten zeigen jetzt im Frontend den Empty-State *"Keine Kontaktdaten gefunden — Closer-Recherche nötig"*.

### Test-Status nach Backfill

101/101 Pipeline-Tests grün (1.12s).

---

## Box 3+5+8 — Code-Sweep (Bug + Quality + a11y) ✅

### Bugs gefixt

1. **`lead-contact-channels.tsx`** — `openChannel` wurde im `useEffect` referenziert *bevor* deklariert. ESLint hat den klassischen TDZ-Bug gefangen. Function vor Effect hoisted.
2. **`command-palette.tsx`** — `useEffect` rief `setValue("")` *synchron* aus, was cascading-renders triggert. Auf `queueMicrotask` umgestellt + render-derived check.
3. **`command-palette.tsx`** — unescaped Quote in JSX (`„{value}"` → `„{value}&ldquo;`).
4. **`bundesanzeiger.py`** — Dead-Code: `search_url`-Variable nie verwendet, entfernt.

### Code-Quality

- 5 unused imports entfernt (`main.py` 3×, `handelsregister.py`, `online_presence.py`, `insolvency.py`, `supabase_client.py`, `bayes.py`).
- ESLint Errors: **13 → 0**. Verbleibende `as any` Casts in `actions.ts` + `queries.ts` sind bewusst dokumentiert (Supabase-SSR-Type-Inference-Bug, mit ESLint-disable-Block + Kommentar).
- Added `audit_log`-Type zur `Database`-Definition (war vorher `as never`-Hack).

### Accessibility-Fixes

- **`lead-contact-channels.tsx`** Copy-Button: `aria-label` + `type="button"` + `focus-visible:ring-2`.
- Show-All-Button: `aria-expanded` + Focus-Ring.
- Bestehende Lucide-Icons in `LeadRating` haben jetzt `ComponentType<{className?: string}>` statt `any`.

### Bug-Hunt — Nichts gefunden

- ✅ Anti-Filter-Edge-Cases: bestehende 29 Tests in `test_anti_filters.py` covern None, leere Strings, ß/Umlaute, Mojibake.
- ✅ Race-Conditions Multi-Channel: kein concurrent-update-Pfad existiert (immer Server-Action mit single transaction).
- ✅ Null-Safety JSONB: `contact_channels` hat `not null default '[]'`, Frontend hat Fallback-Logic.
- ✅ Audit-Log-Konsistenz: alle 4 Server-Actions schreiben in `audit_log`.

### Test-Status

- **101/101 Pipeline-Tests grün** (0.76s).
- **TypeScript: 0 errors.**
- **ESLint: 0 errors.**



