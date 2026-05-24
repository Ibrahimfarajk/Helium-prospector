# Pre-Mortem — helium-prospector

**Datum:** 2026-05-24 (Phase 1.6)
**Frage:** Stell dir vor, in 2 Wochen ist das System gescheitert. Top-5-Ursachen?

Diese Risiken sind ins Design eingeflossen — nicht als "wir denken später drüber nach", sondern als konkrete Mitigations-Mechanismen direkt in Tabellen/Code-Pfaden.

---

## Ursache 1 — Captcha-Eskalation killt den Crawler (35%)

### Was passiert ist
`handelsregister.de` und/oder `unternehmensregister.de` haben aggressivere Anti-Bot-Maßnahmen aktiviert. Nach den ersten 2-3 Tagen werden alle Crawl-Requests mit Captcha beantwortet. Die Pipeline produziert null neue Bekanntmachungen, der Closer hat nichts zum Anrufen, das ganze System ist tot.

### Frühwarnsignal
- `crawl_runs.captchas_hit / pages_fetched > 30 %` in 2 aufeinanderfolgenden Runs
- `crawl_runs.bekanntmachungen_found = 0` in einem normal funktionierenden Run

### Design-Mitigation
1. **`crawl_runs`-Tabelle** trackt Captcha-Hits separat — keine Detektion via Bauchgefühl
2. **playwright-stealth** + realistische User-Agents + 8-12 s jitter zwischen Requests
3. **Persistente Browser-Profile**: Cookies/LocalStorage behalten zwischen Runs → menschlicheres Verhalten
4. **Notification-Webhook** an Admin (Email oder Discord) wenn Captcha-Rate >20 %
5. **Manual-Solving-Modus** im Admin-UI: bei Captcha-Block kann Admin in einem Sub-View das Captcha von Hand lösen, Cookie wird gespeichert
6. **Fallback-Quelle vor-evaluiert**: `OffeneRegister.de`-Bulk-Snapshot (2017-2019, alt aber als Baseline-Lookup für Unternehmens-Stammdaten brauchbar)

---

## Ursache 2 — Closer öffnet die App nie, sie ist tot (20 %)

### Was passiert ist
Der Closer ist gewohnt, Leads per Email oder WhatsApp zu bekommen. Eine eigene Web-App ist ihm fremd. Nach 2-3 Login-Versuchen, der Login-Flow ist unklar oder VPN-Issues aus Türkei/UAE, lässt er es bleiben. Wir haben die schönste App, aber niemand nutzt sie.

### Frühwarnsignal
- `audit_log` zeigt keine Closer-Login-Events in den ersten 72 h nach Account-Anlage
- `lead_activities` mit `user_id=<closer>` bleibt leer

### Design-Mitigation
1. **Email-Digest**: täglich 06:30 Berlin gehen die Top-3-Leads des Tages als kompakter HTML-Email an den Closer raus — Login-Link öffnet direkt das Lead-Detail
2. **Magic-Link-Login**: Supabase Magic-Link statt Passwort-Eingabe → kein Passwort-Vergessen-Drama
3. **Onboarding-Tour** beim ersten Login (5 Steps, dismissable, Shortcut-Cheatsheet als Card)
4. **`profiles.last_seen_at`** wird bei jedem Request aktualisiert → Admin-Dashboard zeigt "Closer war seit 4 Tagen nicht aktiv" + 1-Click "Erinnerung senden"

---

## Ursache 3 — Lead-Qualität reicht nicht / Bayes ist mis-kalibriert (15 %)

### Was passiert ist
Die Bayes-LRs basieren auf Recherche, nicht auf Closer-Feedback. Nach 20 Leads hat der Closer 0 echte Gespräche geführt — entweder weil die "Top-Leads" gar nicht so top sind oder weil die Persona-Hypothese (Praxisverkäufer Q3/Q4, Exit-GmbH-Verkäufer) für das aktuelle Marktzeitfenster falsch ist (wir sind Ende Mai, nicht Q4).

### Frühwarnsignal
- Nach 20 T1-Leads keine `lead_activities` mit `activity_type = 'call_completed'` von >2 Min Gespräch
- Closer setzt Status auf `closed_lost` oder ignoriert Lead bei >70 % der T1-Leads

### Design-Mitigation
1. **Feedback-Buttons im Lead-Detail**: Quick-Buttons ("Telefon nicht erreichbar", "Falsche Person", "Persona-Mismatch", "Trigger zu alt", "Anderes") → Daten für Bayes-Re-Kalibrierung
2. **`score_breakdown` als JSONB** in `leads` → jede LR-Anwendung pro Lead nachvollziehbar, Admin kann analysieren "T1-Leads ohne Conversion — was haben sie gemeinsam?"
3. **Admin-LR-Editor** (Phase-4-Ziel): Admin kann Likelihood-Ratios anpassen, Re-Scoring lauf-bereit
4. **A/B-Test Cohort-Tracking**: erste 10 Leads kriegen `cohort=v1`, nächste 10 mit angepassten LRs `cohort=v2` → Closing-Rate-Vergleich

---

## Ursache 4 — Supabase-Pause oder GitHub-Actions-Quota-Erschöpfung (15 %)

### Was passiert ist
**Sub-A: Supabase Free pausiert nach 7 Tagen Inaktivität.** Bei DB-Pause schlagen Pipeline-Pushes fehl, Frontend gibt 500er.
**Sub-B: GitHub Actions** hat im Public-Repo zwar unlimited Minutes, aber im Private-Repo nur 2.000/Monat. Wenn wir aus Datenschutz-Gründen Private wählen + Daily-Crawl mit 30 Min Laufzeit = ~900 Min/Monat = 45 % Quota. Bei Retries und Längere Runs schnell durch.

### Frühwarnsignal
- Pipeline-Log "DB unreachable" oder Supabase-API 503
- GitHub-Actions-UI zeigt "Quota exceeded" Banner

### Design-Mitigation
1. **Supabase Keep-Alive**: Vercel Cron pingt 1×/Tag einen leichten Endpoint (`/api/health` → trivial SELECT auf `profiles`) — innerhalb der 2-Cron-Limit von Vercel Hobby
2. **Pipeline-Push selbst** = täglicher DB-Touch → keine 7-Tage-Lücke möglich solange Pipeline läuft
3. **GitHub-Actions-Run-Time-Budget**: Pipeline-Code zwingt sich auf max 60 Min Laufzeit (mit timeout-context), abgebrochene Runs vermeiden Quota-Verbrauch
4. **Public-Repo-Empfehlung**: Code (ohne Daten, ohne .env) öffentlich → unlimited Actions-Minutes. Sensitive Daten ohnehin nur in Supabase, nicht im Code.

---

## Ursache 5 — DSGVO-Beschwerde + Issuer-Druck (10 %)

### Was passiert ist
Ein angerufener Lead beschwert sich bei der BNetzA oder direkt bei Star Oil Production GmbH (Hamburg). Resch-Anwälte (die bereits NASCO warnen) bekommen Wind davon und veröffentlichen. Der Issuer (= unser Provisions-Geber) zieht die Notbremse — wir verlieren die Provisionsvereinbarung. System ist nicht "kaputt", aber wirtschaftlich tot.

### Frühwarnsignal
- Email-Eingang bei Star-Oil-Production mit Beschwerde-Subject (nicht direkt detektierbar)
- Resch-Anwälte-Newsfeed oder BSZ-e.V.-Warnung mit "Pinta Dome" oder "Star Oil Production" Erwähnung
- Closer berichtet: "Lead hat gedroht, Anwalt einzuschalten"

### Design-Mitigation
1. **`leads.do_not_contact`** + **`leads.do_not_contact_reason`** als hartes Flag — bei Setzen propagiert über alle Closer (RLS-policy filtert raus)
2. **Audit-Log** lückenlos für jeden Lead-Touch (wer-wann-was) → bei Beschwerde rückwirkend transparent
3. **Closer-Diskretions-Guideline** in OPERATIONS.md (Phase 4): keine Aufdringlichkeit, "Soll ich auflegen?"-Soft-Exit-Door, max 1 Folgekontakt nach Nicht-Reaktion
4. **Issuer-Distanz**: Closer ruft NICHT als "Star Oil Production"-Mitarbeiter an, sondern als unabhängiger Vermittler. Issuer-Name fällt erst nach Interesse-Signal vom Lead
5. **Soft-Delete via `deleted_at`** statt Hard-Delete bei DSGVO-Löschung — bei Beschwerde-Audit ist die Datenbasis noch da, nur für UI gefiltert

---

## Ursache 6 (Bonus, <5 %) — Multi-Closer-Konflikt

### Was passiert ist
Zwei Closer rufen denselben Lead an. Lead ist verwirrt, klagt über "spam", Reputations-Schaden.

### Design-Mitigation (schon im Schema)
- **`lead_assignments`** mit unique-partial-index `(lead_id) WHERE released_at IS NULL` → datenbankseitig erzwungen, nur ein aktiver Closer pro Lead
- "Claim"-Flow im UI: vor erstem Anruf muss Closer auf "Übernehmen" klicken, dann ist Lead "geblockt" für andere

---

## Was das Pre-Mortem an Phase-2-Architektur ändert

1. **`crawl_runs`-Tabelle** ist Pflicht (Frühwarnung U1) — nicht "nice to have"
2. **Audit-Log** ist Pflicht (U5) — nicht später nachrüstbar
3. **Notification-Webhook**-Infrastruktur muss früh angelegt werden — Discord-Webhook reicht für MVP
4. **Email-Digest** für Closer (U2) → benötigt Email-Sender (Resend free tier: 3.000 Emails/Monat, gratis)
5. **Feedback-Buttons** im UI (U3) → Pflicht in Phase 3, nicht Phase 4
6. **`leads.do_not_contact`** ist hard-Flag (U5) → schon im Schema

Alle 6 Punkte sind im aktuellen DB-Schema und in der Architektur enthalten.

---

## Was NICHT mitigiert ist (bewusster Trade-off)

- **Marktzeitfenster-Risiko**: Wir bauen jetzt im Mai. Praxisverkäufer-Trigger sind Q3/Q4-Saisonal. Erste 2-3 Wochen werden wenig "Heiße" Praxisverkäufer-Leads kommen. Wir akzeptieren das und konzentrieren uns auf GmbH-Exit-Leads die ganzjährig erscheinen.
- **Closer-Onboarding-Lernkurve**: 2-3 Tage bis Closer mit Dossier-Format vertraut ist. Nicht mitigierbar, nur über kurzes Onboarding-Doc.
- **Lange Sales-Cycle bei 38k EUR Ticket**: Strukturell. TTFD bleibt 6-10 Wochen.

---

## Tracking-Dashboard für die Pre-Mortem-Signale (Phase 3)

Auf dem Admin-Dashboard sollte sichtbar sein:

| Signal | Quelle | Threshold |
|---|---|---|
| Captcha-Hit-Rate letzte 7 Tage | `crawl_runs` | >20 % = warning, >40 % = alert |
| Closer-Active-Status | `profiles.last_seen_at` | >48h = warning, >7 d = alert |
| T1-Lead-Conversion letzte 30 Tage | `leads`+`lead_activities` | <5 % = warning |
| Supabase-DB-Last-Touch | DB query timestamp | >5 d = warning |
| GitHub-Actions-Quota-Used (Monat) | extern (gh API) | >70 % = warning |
| do_not_contact-Rate letzte 30 Tage | `leads` | >5 % = alert (Issuer-Risk-Indikator) |
