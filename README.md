# helium-prospector

> Lead-Generation + CRM für Helium-Direktbeteiligungen (Pinta Dome / Star Oil Production GmbH)

## Was ist das?

Vollautomatisches Lead-System + Multi-User-CRM für Cold-Outbound im DACH-Markt:

- **Tägliche Crawler-Pipeline** auf `handelsregister.de` Bekanntmachungen (GF-/Anteilseigner-Wechsel, Holding-Neugründungen, Kapital-Erhöhungen)
- **Bayesian Scoring** mit Trigger-Frische, Vermögen, Persona-Hinweisen
- **1-Seiten-Dossier** für Closer (90 Sekunden lesbar)
- **Champions-League CRM** (Linear/Stripe/Vercel-Niveau): Dashboard, Lead-Detail, Command-Palette, Keyboard-Shortcuts
- **Multi-User** mit Admin + Closer-Rollen, Row-Level-Security
- **0 EUR laufende Kosten** (Vercel Hobby + Supabase Free + GitHub Actions)

## Architektur

Siehe [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
helium-prospector/
├── web/        — Next.js 15 CRM (Vercel)
├── pipeline/   — Python Crawler (GitHub Actions Cron)
├── shared/     — db_schema.sql (Source of Truth)
└── docs/       — Architektur, Pre-Mortem, Operations, Build-Log
```

## Datenfluss

```
GitHub Actions (06:00 Berlin)
  → Python Pipeline
    → handelsregister.de Crawl
    → Bundesanzeiger Cross-Reference
    → Bayesian Scoring
    → Dossier-Generator
  → Supabase Postgres
  → Next.js Web App
  → Closer Cold-Call
```

## Strategische Grundlagen

Drei Dokumente in der Root, die das Warum erklären:

| Dokument | Inhalt |
|---|---|
| [`RECHERCHE_ANALYSE.md`](RECHERCHE_ANALYSE.md) | V2.3 final — Investor-Profile, HNW-Detection, Quellen-Landschaft, Bayes-Scoring, TTFD |
| [`MVLT_V2.2_ERGEBNISSE.md`](MVLT_V2.2_ERGEBNISSE.md) | Validierungs-Test der Hypothesen — was funktioniert, was nicht |
| [`RECHERCHE_V1_BACKUP.md`](RECHERCHE_V1_BACKUP.md) | V1-Recherche als Kontext (nicht als Vorgabe) |

## Setup (Phasen 2-4 noch ausstehend)

### Voraussetzungen

- Node 24+, pnpm
- Python 3.11+
- Supabase-Account (free tier)
- Vercel-Account (Hobby)
- GitHub-Repo

### Quick-Start

```bash
# Web
cd web
pnpm install
pnpm dev

# Pipeline
cd pipeline
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python -m helium_pipeline.main --dry-run
```

Detaillierte Operations-Doku folgt in Phase 4 in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Lizenz / Hinweise

Privates Projekt. Personen-Daten unter DSGVO-Schutz. Nutzung nur durch autorisierte Closer.

## Build-Log

Jede technische Entscheidung wird in [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) festgehalten.
