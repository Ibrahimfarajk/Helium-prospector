# QA Audit — A-Z Bug-Hunt + Optimization Pass

**Datum:** 2026-05-24
**Methodik:** Code-Review + Live-Tests gegen Production + Schema-Inspection

---

## Findings

### 🔴 CRITICAL (System-broken oder Daten-Risk)

| # | Issue | Stelle |
|---|---|---|
| C1 | **PDF-Button im Lead-Detail hat keinen onClick — funktioniert nicht** | `app/(app)/leads/[id]/page.tsx:114` |
| C2 | **Status-Pipeline schreibt direkt auf `leads`-Tabelle, nicht View** — funktioniert, aber bei Closer-Role-RLS könnte das brechen | `actions.ts:22` |

### 🟠 HIGH (Funktional, sichtbar für User)

| # | Issue | Stelle |
|---|---|---|
| H1 | `markDoNotContact` Server-Action existiert, aber **kein UI-Button um es auszulösen** | `actions.ts:69` |
| H2 | **Login-Page zeigt keinen Fehler** wenn Email-Format invalid ist (kein client-side validation) | `login/page.tsx` |
| H3 | **Lead-Detail-Page: Sort-Select hat Browser-Default-Style**, kein shadcn-Pattern | `leads-table.tsx:142` |
| H4 | **Best-Call-Window erkennt nicht "Geschäftsführerin"** (nur "Geschäftsführer", case-sensitive Pattern-Match misst) | `dossier/generator.py:24` |
| H5 | **`datetime.utcnow()` deprecated** in Python 3.12+; produziert naive datetime ohne TZ | `main.py`, `models.py` |

### 🟡 MEDIUM (UX/Polish/Performance)

| # | Issue | Stelle |
|---|---|---|
| M1 | **Pipeline schreibt kein audit_log-Entry** für Lead-Creates | `main.py` |
| M2 | **`as any` Casts** in Server Actions — type-safety lost | `actions.ts` |
| M3 | **Bayes-Math: Posterior wird 34.0% oben, 34.00% rechts** angezeigt — inkonsistent | `lead/[id]/page.tsx` |
| M4 | **Sidebar Hover-State ist subtil**, aktiv-State könnte deutlicher sein | `sidebar.tsx` |
| M5 | **Cmd+K "Tagesplan exportieren" / "Pipeline neu starten" sind Stubs** — keine Action | `command-palette.tsx` |
| M6 | **Login Magic-Link 302-redirect** — könnte als Warning gelabelt werden ("Email kann 30 Sek dauern") | `login/page.tsx` |
| M7 | **Settings-Page** zeigt User-Stats aber kein UI für Closer-Verwaltung (Admin-only feature fehlt) | `settings/page.tsx` |

### 🟢 LOW (Nice-to-have)

| # | Issue | Stelle |
|---|---|---|
| L1 | Demo-Mode-Code (`demo.ts`) wird in Production-Bundle gezogen | `lib/db/demo.ts` |
| L2 | `_layout.tsx` font-class duplikat (LF-Warnings beim git add) | git config |
| L3 | Pipeline-Logs schreiben `email`/`phone` ins stdout — DSGVO sub-optimal | `main.py` |
| L4 | `Lead.score_breakdown` JSONB ist nicht typsicher im TS — könnte runtime kaputt sein | `db/types.ts` |
| L5 | Bei Lead-Detail wird `best_call_window` aus DB UND Fallback "Di/Mi 10-12" gezeigt — DB-Wert ist autoritativ aber Fallback verwirrt | `page.tsx:104` |

