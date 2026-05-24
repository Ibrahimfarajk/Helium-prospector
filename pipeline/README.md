# helium-pipeline

Python-Pipeline: Crawl handelsregister.de → Score → Dossier → Supabase.

## Setup (lokal)

```bash
cd pipeline
python -m venv .venv
.venv\Scripts\activate          # Windows
# bzw. source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium
```

`.env` aus Root `.env.example` ableiten.

## Lokaler Test

```bash
# Dry-Run (kein DB-Write, nur Konsole)
helium-pipeline run --dry-run --max-pages 1

# Echter Run
helium-pipeline run

# Nur Scoring-Tests
pytest tests/test_scoring.py -v
```

## Architektur

```
helium_pipeline/
├── models.py             # Pydantic v2 Schemas
├── settings.py           # Env-Konfiguration
├── logging_setup.py      # structlog JSON-Konfig
├── crawlers/
│   ├── handelsregister.py    # Playwright + stealth
│   └── bundesanzeiger.py     # gezielte EK-Lookups
├── scoring/
│   └── bayes.py          # Hard-Gates + Likelihood-Ratios
├── dossier/
│   └── generator.py      # Markdown-Template + Hook-Mapping
├── telephony/
│   └── phone_finder.py   # Google + Impressum-Parsing
├── db/
│   └── supabase_client.py
└── main.py               # CLI orchestrator
```
