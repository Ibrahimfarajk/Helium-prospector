# MORGEN WEITER — Sauberer Wiedereinstieg

> **Stand:** Ende 2026-05-24, ~02:30 UTC
> Lies das hier ZUERST. Dann hast du in 2 Min Kontext.

---

## TL;DR — Was war gestern, was ist heute

**Gestern fertig (Phase 1-4 + QA-Pass):**
- Vollständiges Lead-Generation-System (Python-Pipeline + Next.js CRM)
- Live deployed auf Vercel mit echter Supabase-DB
- 13 Demo-Leads in der DB
- Admin-Account (ibrahimk94@outlook.de) eingerichtet, Login funktioniert
- 12/12 Python-Tests grün, Next.js Build clean
- QA-Audit mit 12 Findings durchgeführt + alle behoben
- E2E-Test-Suite: 25/28 pass auf Production

**Heute zu tun (Phase 4 abschließen + Phase 5 starten):**
1. GitHub-Actions-Secrets setzen → Daily-Cron läuft
2. 2-3 Closer-Accounts anlegen
3. Live-Crawler handelsregister.de fertigstellen (TODO Phase 5)
4. Bundesanzeiger-Fix mit Playwright (TODO Phase 5)

---

**Update 2026-05-25 (Phase 5 Tag 2 abgeschlossen):**
- ✅ 3 Closer-Test-Accounts (ibrahimk94+closerN@outlook.de) angelegt
- ✅ Live-Crawler handelsregister.de fertig (Cookie + Nav + Parser)
- ✅ Bundesanzeiger auf Playwright migriert
- ✅ Phone-Finder gehärtet (Behörden-Block + Service-Number-Filter)
- ✅ Closer-Feedback-UI (Top/OK/Schlecht Rating-Card im Lead-Detail)
- ⚠️ Vollständiger Live-Pipeline-Smoke-Test pendent (IP-Ban-Schutz: max 4 Sessions/Tag eingehalten)
- ⏳ User-Action: GitHub-Secrets-Setup (5 Min)

---

## Live-Services (alle ✅)

| Service | URL | Status |
|---|---|---|
| **App (Production)** | `https://helium-prospector.vercel.app` | ✅ Live |
| **GitHub Repo** | `https://github.com/Ibrahimfarajk/Helium-prospector` | ✅ Public, Auto-Deploy aktiv |
| **Supabase Projekt** | `https://supabase.com/dashboard/project/jkqgpfbnplthchifwhqy` | ✅ Free-Tier, eu-central-1, 13 Leads |
| **Vercel Projekt** | `https://vercel.com/ibrahim-s-projects10/helium-prospector` | ✅ Production-Build erfolgreich |

---

## Credentials — wo zu finden, NICHT hier

| Was | Wo |
|---|---|
| Supabase URL + Keys (anon, service_role) | `web/.env.local` und `pipeline/.env` (lokal, gitignored) |
| DB-Passwort | `pipeline/.env`-Snippet von vorgestern in deinem Passwort-Manager (du hattest es mir geschickt: `UduZGmP7GW6MzhP4`) |
| Vercel-CLI-Token | Schon auf deinem Rechner als `ibrahimk94-6261` eingeloggt (siehe `vercel whoami`) |
| GitHub-Token | git-Remote ist konfiguriert, kein Token-Eintippen nötig |

---

## Was noch OFFEN ist

### 1. GitHub-Actions-Secrets (5 Min, blockiert Cron-Pipeline)
Siehe `docs/GITHUB_SECRETS.md`. Du musst manuell in GitHub Settings → Secrets folgende setzen:
- `SUPABASE_URL` = `https://jkqgpfbnplthchifwhqy.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` = (aus `pipeline/.env`)
- `SUPABASE_ANON_KEY` = (aus `pipeline/.env`)
- `DISCORD_WEBHOOK_URL` = (optional, für Alerts)

Sobald gesetzt: Daily-Cron läuft täglich 05:00 UTC = 07:00 Berlin.

### 2. Closer-Accounts anlegen (10 Min)
2-3 Closer-Accounts in Supabase + profile-Rows mit role=closer.
Anleitung: `docs/OPERATIONS.md` → Closer-Onboarding.

### 3. Phase 5: TODOs aus Build-Log
- **handelsregister.de Cookie-Banner-Akzept-Flow** im Live-Crawler (`pipeline/helium_pipeline/crawlers/handelsregister.py`)
- **Bundesanzeiger** auf Playwright migrieren statt httpx (302-Errors fixen)
- **Phone-Finder False-Positive-Filter** weiter verschärfen (immer noch behörden-domain-Treffer möglich)
- **Closer-Feedback-Buttons** im Lead-Detail für Bayes-Re-Kalibrierung (siehe PRE_MORTEM U3)

---

## Wiedereinstieg morgen — EXAKT in dieser Reihenfolge

### Schritt 1 — Projekt-Verzeichnis öffnen + Status prüfen

PowerShell oder Bash, in `C:\Users\ibrah\helium-prospector`:

```bash
cd C:\Users\ibrah\helium-prospector
git status
git pull origin main
```

`git status` sollte sagen: "working tree clean, on branch main". `git pull` falls von Vercel/anderem Rechner noch Commits ausstehen.

### Schritt 2 — Live-Check (Sanity)

```bash
curl -s -o /dev/null -w "App: %{http_code}\n" https://helium-prospector.vercel.app/api/keepalive
```

Erwartet: `App: 200`. Wenn 500/503: Supabase pausiert oder Vercel-Build-Issue.

### Schritt 3 — Python-Tests laufen lassen (Smoke-Check)

```bash
cd pipeline
python -m pytest tests/ -v
```

Erwartet: `12 passed`.

### Schritt 4 — Magic-Link für Login generieren

```bash
cd C:\Users\ibrah\helium-prospector\pipeline
python -c "from dotenv import load_dotenv; load_dotenv(); from helium_pipeline.db.supabase_client import SupabaseRepo; r = SupabaseRepo().client.auth.admin.generate_link({'type': 'magiclink', 'email': 'ibrahimk94@outlook.de', 'options': {'redirect_to': 'https://helium-prospector.vercel.app/auth/callback'}}); print(r.properties.action_link)"
```

→ Output ist der Link, einfach im Browser öffnen → bist eingeloggt im Dashboard.

(Alternativ: Auf https://helium-prospector.vercel.app/login dein Email eintragen und auf den echten Magic-Link in deiner Inbox warten.)

### Schritt 5 — Wo weitermachen?

Optionen, sortiert nach Aufwand:

**A) GitHub-Secrets setzen (5 Min)** — siehe `docs/GITHUB_SECRETS.md`
Schalte den Daily-Cron ein. Nach dem Setup ist die Pipeline self-sustaining.

**B) Closer-Account anlegen (10 Min)** — siehe `docs/OPERATIONS.md` § Closer-Onboarding
Damit ein zweiter Test-User existiert für Multi-User-Tests.

**C) Phase-5-Bauschritt wählen** (siehe BUILD_LOG.md). Reihenfolge nach Impact:
1. **handelsregister.de Live-Crawler** (~4-6h) — eliminiert Mock-Source, echte Leads
2. **Bundesanzeiger Playwright-Migration** (~2-3h) — bessere EK-Anreicherung
3. **Closer-Feedback-Buttons** im UI (~2h) — Bayes-Kalibrierung-Loop

---

## Wichtige Dateien zum schnellen Re-Orient

| Datei | Inhalt |
|---|---|
| `RECHERCHE_ANALYSE.md` | V2.3-Strategie (warum dieses Produkt, diese Persona, diese Quellen) |
| `MVLT_V2.2_ERGEBNISSE.md` | Validierungs-Test-Ergebnisse (was funktioniert, was nicht) |
| `docs/ARCHITECTURE.md` | Tech-Stack + Datenfluss |
| `docs/PRE_MORTEM.md` | Top-5-Risiken und Mitigationen |
| `docs/BUILD_LOG.md` | **Alle Entscheidungen Phase 1-4 + QA** chronologisch |
| `docs/QA_AUDIT.md` | 12 Findings + Fixes + E2E-Test-Resultate |
| `docs/SUPABASE_SETUP.md` | DB-Setup-Anleitung (für Replikation) |
| `docs/VERCEL_DEPLOY.md` | Deploy-Anleitung (für Replikation) |
| `docs/GITHUB_SECRETS.md` | Actions-Secrets-Setup |
| `docs/OPERATIONS.md` | Täglicher Use + Notfall-Manual |

---

## Was passiert wenn du heute Nacht zwischen jetzt und morgen NICHTS machst

- ✅ Vercel-App bleibt live (Vercel Hobby ist 24/7)
- ✅ Supabase bleibt aktiv (Vercel Cron pingt täglich — Keep-Alive-Endpoint `/api/keepalive`)
- ⚠️ GitHub-Actions Cron läuft 05:00 UTC ABER ohne Secrets-Setup wird die Pipeline failen — **das ist OK**, du hast nur 13 Demo-Leads und KEIN echtes Crawling läuft noch
- ✅ Daten in Supabase bleiben unverändert

---

## Vor dem Ausschalten — kurze Sanity-Liste

- [x] Alle Local-Edits committed + pushed (`git status` clean)
- [x] `web/.env.local` und `pipeline/.env` mit echten Credentials (lokal, nicht im Repo)
- [x] Admin-User in Supabase auth.users mit `ibrahimk94@outlook.de` + role=admin in profiles
- [x] 13 Leads in Supabase live verfügbar
- [x] Vercel Production-Deploy `cfe1ca3` (oder neuer) → erreichbar
- [x] GitHub-Repo `Ibrahimfarajk/Helium-prospector` Public mit allen Commits

---

## DEIN ERSTER BEFEHL MORGEN

```bash
cd C:\Users\ibrah\helium-prospector && git pull && cat docs/MORGEN_WEITER.md
```

Das öffnet dieses Dokument im Terminal. Dann oben in der Datei steht "Wiedereinstieg morgen", und du folgst der Reihenfolge.

Wenn du Claude wieder startest: zeig ihm einfach diese Datei. Er hat dann sofort vollen Kontext.
