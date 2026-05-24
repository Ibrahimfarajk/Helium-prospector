# Pre-Mortem: Live-Crawler handelsregister.de + Bundesanzeiger

**Datum:** 2026-05-25 Phase 5
**Frage:** "Es ist 18:00. Der Live-Crawler hat das System killed. Was ist passiert?"

---

## Top-5 Risiken sortiert nach Wahrscheinlichkeit × Impact

### 🔴 R1 — IP-Ban während Entwicklungs-Tests (Wahrscheinlichkeit 30%, Impact HOCH)

**Szenario:** Beim Iterieren des Cookie-Banner-Flows feuern wir 50+ Requests in 30 Min ab. handelsregister.de erkennt das Pattern, bannt unsere Heim-IP für 24-72h. Pipeline kann lokal NICHT mehr getestet werden, GitHub-Actions (andere IP) läuft noch, aber lokal Dev ist blockiert.

**Mitigation:**
1. **Maximale Test-Frequenz: 1 Request alle 30 Sekunden, max 10 Tests/Stunde**
2. Erst die UI-Discovery komplett gegen lokales HTML-Dump (snapshot von letzter Session) entwickeln
3. Bei Test gegen Live: zwischen jedem Run 2-3 Min Pause
4. **Persistent Browser-Profile** (`~/.helium-pipeline/browser-profile`) — keine neuen Cookies pro Run
5. Wenn 2x Captcha hintereinander → STOPP, 24h Pause

### 🔴 R2 — Captcha-Eskalation kickt in (Wahrscheinlichkeit 25%, Impact HOCH)

**Szenario:** handelsregister.de hat hCaptcha hinter dem Cookie-Banner. Stealth-Mode reicht nicht. Jeder Crawl wird mit Captcha-Page beantwortet.

**Mitigation:**
1. **Schritt 1: Probier OHNE Captcha mit guten Stealth-Settings** — Fingerprint, locale=de-DE, persistent profile
2. **Schritt 2: Manuelles Captcha-Lösen einmal** durch Headless=false, Captcha-Cookie wird gespeichert, persistent profile übernimmt für ~24h
3. **Schritt 3: Fallback OffeneRegister.de-Bulk-Snapshot** (2017-2019 Daten) — als Baseline mit alter Identity-Resolution kombinieren
4. Niemals headless-true testen bevor wir den vollen Flow validiert haben

### 🟠 R3 — Cookie-Banner-Selektoren brüchig (Wahrscheinlichkeit 40%, Impact MITTEL)

**Szenario:** Selektor für "Akzeptieren"-Button funktioniert heute, nach UI-Update von handelsregister.de in 4 Wochen nicht mehr. Pipeline silent-failed.

**Mitigation:**
1. **Mehrere Selektoren als Fallback-Chain** — versuche Text-basiert ("Akzeptieren") und ID-basiert
2. **Telemetrie:** wenn Cookie-Banner-Click nicht clicked → `crawl_runs.notes = "cookie_banner_missing"` → Admin-Alert
3. Selektoren in einer **separaten config-Datei**, damit fix in 5 Min ohne Code-Push
4. **Health-Check-Test** in CI: lädt eine bekannte HRB-Detail-Seite und prüft ob "GmbH" im HTML

### 🟠 R4 — Bundesanzeiger 302-Redirect bleibt (Wahrscheinlichkeit 50%, Impact MITTEL)

**Szenario:** Aktuelle httpx-basierte Bundesanzeiger-Suche redirected zu /error. Auch mit Playwright könnte Captcha-Wall davorstehen.

**Mitigation:**
1. **First-Approach: Playwright + Persistent Profile** — viele JS-Sites verlangen aktive Session/Cookies
2. **Second-Approach: Direkter Treffer per HRB-URL-Pattern** — vermutlich gibt es `/v2/companies/{hrb}` o.ä.
3. **Acceptance:** EK-Anreicherung ist nice-to-have, NICHT critical. Ohne EK → Lead kommt trotzdem in Tier-Berechnung (nur ohne EK-LR). Wenn Bundesanzeiger 100% blocked, pipeline läuft trotzdem.

### 🟡 R5 — Crawler liefert duplicate Bekanntmachungen (Wahrscheinlichkeit 20%, Impact NIEDRIG)

**Szenario:** Pagination-Logik fängt einen Eintrag in mehreren Seiten doppelt. Unique-Constraint `(hrb_nummer, bekanntmachung_date, bekanntmachung_type)` greift → INSERT failed → Lead nicht erstellt → Stille.

**Mitigation:**
1. ON CONFLICT DO NOTHING ist schon im Code (`ignore_duplicates=True` in supabase_client)
2. Telemetrie: `crawl_runs.bekanntmachungen_found` zeigt Raw-Count, vs. tatsächlich neue Inserts
3. Wenn Diff >30%: alert

---

## Konsequenzen für das Vorgehen (HEUTE)

1. **ERST Dump speichern, DANN Crawler bauen.** Eine einzige Live-Session am Morgen, HTML capturen, dann offline UI-Discovery.
2. **Live-Tests rate-limited:** max 1 Request alle 30 Sek, max 5 Tests/h
3. **Captcha-Detector als HARD GATE:** bei Captcha-Page → sofort stop + log, kein Retry
4. **Persistent Browser-Profile** vermeidet Fresh-Fingerprint-Detection
5. **Bundesanzeiger ist SECONDARY** — wenn schwierig, skip für heute, Pipeline läuft auch ohne

---

## Akzeptiertes Risiko

- Es kann passieren, dass meine Heim-IP für 24-72h vorübergehend gebannt wird.
- Workaround: GitHub-Actions läuft von Vercel/GitHub-Cloud-IPs, also Cron würde noch funktionieren.
- Lokal-Dev kann dann nur gegen Mock-Source laufen bis Ban abgelaufen.

**Ich frage NUR DICH wenn:** ich nach 3 Test-Runs konsequent Captcha sehe oder eine UI komplett unverständlich ist.
