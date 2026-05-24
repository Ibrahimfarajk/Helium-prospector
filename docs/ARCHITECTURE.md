# helium-prospector — Architektur

**Stand:** 2026-05-24, Phase-1-Entscheidung
**Constraint:** 0 EUR laufende Kosten, multi-user, online verfügbar, DSGVO-konform

---

## 1. Tech-Stack (final)

### Frontend (`/web`)
- **Next.js 15** (App Router, React Server Components, Server Actions)
- **TypeScript 5** strict mode
- **TailwindCSS 4** + **shadcn/ui** (copy-paste, kein bundle bloat)
- **Inter Variable Font** via `next/font` (Geist als Alternative, gleichwertig)
- **Framer Motion** für Mikro-Animationen (Modal/Drawer)
- **cmdk** für Command-Palette
- **react-hook-form + zod** für Formulare
- **sonner** für Toasts
- **lucide-react** für Icons (klein, tree-shake-friendly)
- **@tanstack/react-table** für die Lead-Liste (Sorting/Filtering/Virtualization)

### Backend / Daten
- **Supabase** (Postgres 15 + Auth + Row-Level-Security + Storage)
- **Drizzle ORM** (statt Prisma — leichter, edge-friendly, RLS-kompatibel, generiert TypeScript-Types)
- **Next.js Server Actions** für Mutations (typesafe, kein API-Router-Boilerplate)
- **@supabase/ssr** für serverseitiges Auth-Handling

### Lead-Pipeline (`/pipeline`)
- **Python 3.11**
- **Playwright** (Async) + **playwright-stealth** für Anti-Detection
- **pydantic v2** für Schema-Validierung
- **httpx** statt `requests` (async, modern)
- **selectolax** statt BeautifulSoup (10× schneller, lxml-basiert)
- **supabase-py** zum Schreiben in DB
- **structlog** für JSON-Logs
- **tenacity** für Retry-Logic

### Hosting / Deployment (alle gratis-tier)
- **Vercel Hobby** (Frontend): 100 GB Bandbreite, automatisches HTTPS, CDN
- **Supabase Free** (DB + Auth): 500 MB DB, 50.000 MAU, 5 GB Bandbreite, **Pause nach 7 Tagen Inaktivität** → Mitigation: Vercel Cron pingt 1×/Tag
- **GitHub Actions** (Python-Cron-Host): 2.000 min/Monat bei public repo, robust, eingebaute Logs, Secrets-Management

### Tests
- **Vitest** für TS (kritische Logik: Scoring-Berechnung, RLS-Smoke-Tests)
- **pytest** für Python (Bayes-Math, Parser-Robustheit)

---

## 2. Abweichungen vom User-Vorschlag

| Vorschlag des Users | Meine Entscheidung | Grund |
|---|---|---|
| Vercel Cron für Pipeline | **GitHub Actions** | Vercel Hobby = 2 Cron-Jobs/Tag max; Playwright-Bundle zu groß für Vercel Functions (250 MB Limit). GH Actions: 2.000 min/Monat gratis, robust, Logs eingebaut. |
| BeautifulSoup | **selectolax** | 10× schneller, lxml-basiert, gleiche API-Ergonomie |
| requests | **httpx** | Async-fähig, modern, gleiche API |
| Prisma (implizit) | **Drizzle ORM** | Leichter (kein Schema-Studio nötig), Edge-kompatibel, exzellente RLS-Integration |

---

## 3. Trade-off-Analyse

### Pros
- Komplett 0 EUR im stationären Betrieb
- Stack ist Standard → riesige Community, AI-Code-Coverage hoch
- Server Components reduzieren Bundle (Lead-Liste schnell)
- Drizzle + TypeScript = end-to-end Type-Safety
- Skalierbar bis 5+ Closer ohne Architektur-Änderung (Supabase Free reicht für 50k MAU)

### Cons
- Supabase pausiert nach 7 Tagen Inaktivität (mitigated via Cron-Ping)
- Vercel Hobby = nicht für kommerzielle Nutzung lt. ToS — bei echter Skalierung muss auf Pro (20$/Monat) gewechselt werden. Kein Showstopper für MVP.
- GitHub Actions Minuten-Limit (2k/Monat) → bei daily Cron mit ~10 min Laufzeit = 300 min/Monat verbraucht, locker im Limit
- Python+TypeScript-Split = zwei Repos-Mental-Models, aber rechtfertigt sich (Playwright-Python ist deutlich ausgereifter als Playwright-Node für Stealth)

### Skalierbarkeit auf 5+ Closer
- Supabase Free reicht für 50k MAU → 5 Closer × tägliche Logins = 150 MAU/Monat → 0,3% Auslastung
- Vercel Hobby: 100 GB Bandbreite → 5 Closer × 10 Views/Tag × 200 KB Payload = 30 MB/Tag = 900 MB/Monat → 0,9% Auslastung
- Bottleneck wird Postgres-Storage sein bei ~100k+ Leads — bei 500 MB free und ~5 KB/Lead = ~100k Leads Headroom. Reicht.

---

## 4. Top-3-Risiken (Tech-Stack-spezifisch)

### Risiko 1: Supabase 7-Tage-Pause killt Pipeline-Pushes
**Wahrscheinlichkeit:** Mittel (nur wenn wir vergessen zu pingen)
**Mitigation:** Vercel Cron pingt Supabase Health-Endpoint 1×/Tag (innerhalb Hobby-2-Cron-Limit), zusätzlich GitHub-Actions-Pipeline schreibt 1×/Tag → effektiv keine 7-Tage-Lücke möglich.

### Risiko 2: handelsregister.de Anti-Bot-Eskalation
**Wahrscheinlichkeit:** Mittel-Hoch (Anti-Bot wird tendenziell aggressiver)
**Mitigation:** playwright-stealth, realistische User-Agents, 8-12s jitter, persistente Browser-Profile (Cookies behalten), bei Captcha → Notification + Manual-Solving-Pfad im Admin-UI.

### Risiko 3: GitHub-Actions kann sensible Daten (Lead-Daten in Logs) leaken
**Wahrscheinlichkeit:** Niedrig wenn diszipliniert
**Mitigation:** structured logging, alle Personen-Daten nur in Supabase nicht im stdout; Secrets ausschließlich via GH Secrets; Public-Repo nur für Code, nicht für DB-Dumps; .env.example committed, .env in .gitignore.

---

## 5. Ordnerstruktur (flat, kein Workspace-Tool)

```
helium-prospector/
├── web/                    # Next.js 15 App
│   ├── app/
│   │   ├── (auth)/         # Login, Register, Reset
│   │   ├── (app)/          # Dashboard, Leads, Settings (auth-protected)
│   │   └── api/            # nur wo Server Actions nicht reichen
│   ├── components/
│   │   ├── ui/             # shadcn/ui primitives
│   │   ├── leads/          # Lead-Liste, Lead-Detail, Dossier-View
│   │   └── shared/         # Layout, Command-Palette, Theme
│   ├── lib/
│   │   ├── db/             # Drizzle schema + queries
│   │   ├── supabase/       # client + server + middleware
│   │   ├── scoring/        # Bayes-Replication (für Display + Updates)
│   │   └── utils/
│   ├── drizzle/            # Migrations
│   └── package.json
│
├── pipeline/               # Python Crawler
│   ├── helium_pipeline/
│   │   ├── crawlers/
│   │   │   ├── handelsregister.py
│   │   │   └── bundesanzeiger.py
│   │   ├── scoring/
│   │   │   └── bayes.py
│   │   ├── dossier/
│   │   │   └── generator.py
│   │   ├── db/
│   │   │   └── supabase_client.py
│   │   ├── telephony/
│   │   │   └── phone_finder.py
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── shared/                 # Schema-Specs cross-stack
│   ├── db_schema.sql       # SOURCE OF TRUTH für Postgres
│   └── lead_format.md      # Dossier-Format-Spec
│
├── docs/
│   ├── ARCHITECTURE.md     # dieses Dokument
│   ├── PRE_MORTEM.md       # Phase-1.6 Risiko-Doku
│   ├── OPERATIONS.md       # wie täglich nutzen (Phase 4)
│   └── BUILD_LOG.md        # kontinuierliches Entscheidungs-Log
│
├── .github/workflows/      # GitHub Actions
│   └── daily-pipeline.yml  # Cron-Job für tägliches Crawl
│
├── README.md
├── .gitignore
└── .env.example
```

---

## 6. Datenfluss

```
GitHub Actions (06:00 Berlin daily)
    │
    ▼
Python Pipeline (helium_pipeline/main.py)
    │
    ├─► Crawl handelsregister.de (Playwright stealth)
    │       ↓
    │       bekanntmachungen_raw  (Supabase, immutable)
    │
    ├─► Cross-Reference Bundesanzeiger (gezielt)
    │       ↓
    │       company-EK angereichert
    │
    ├─► Phone-Finder (Google site-search + Impressum parse)
    │       ↓
    │       contact info
    │
    ├─► Bayesian Scoring (scoring/bayes.py)
    │       ↓
    │       Posterior + Tier
    │
    └─► Dossier-Generator
            ↓
            leads  (Supabase)
                ↓
        Next.js Web App (Closer-Queue)
            ↓
        Closer-Cold-Call
            ↓
        Status-Updates → lead_activities + audit_log
```
