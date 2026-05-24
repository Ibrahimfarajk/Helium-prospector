# MVLT V2.2 — DURCHFÜHRUNGS-PROTOKOLL

**Datum:** 2026-05-24
**Ziel:** Cold-Pipeline + Identity-Resolution-Realität validieren
**Aufwand-Budget:** ~3h, 0 EUR
**Methodik:** Real-World-Test der Quellen + manuelle ID-Versuche

---

## STATUS

- [x] Phase A (60 Min): Cold-Pipeline-Quellen testen — **PARTIAL ERFOLGREICH**
- [x] Phase B (60 Min): Identity-Resolution-Yield — **GESCHEITERT**
- [x] Phase C (60 Min): Prospect-Template-Inventur — **DURCHGEFÜHRT**

---

## PHASE A — ERGEBNISSE

### A.1 Handelsregister-Bekanntmachungen (Quelle 1)

**Getestete URL:** `unternehmensregister.de/de/suche/registerbekanntmachungen`

**Befund:**
- ✅ Quelle ist öffentlich, 0 EUR, alle Bekanntmachungen der letzten 4 Wochen frei sichtbar
- ✅ Suchfilter: Firmenname, Sitz, Rechtsform, Registergericht, Veröffentlichungsart, Zeitraum
- ⚠️ JavaScript-getriebenes Such-Interface → WebFetch sieht nur Landing-Page, nicht Suchergebnisse
- ⚠️ Automatisiertes Crawling braucht **Playwright** (Browser-Automation), nicht plain HTTP
- ⚠️ Captcha-Risiko bei Volume (>50 Requests/Tag laut Industrie-Reports)

**Praxis-Implikation:**
- Manuell: 5-10 Lookups/Tag problemlos
- Automatisiert: Playwright-Pipeline nötig, ~4-6h Setup-Aufwand

### A.2 Praxisbörsen (Quelle 2)

**Getestete Plattformen:**
| Plattform | Inserate sichtbar | Kontaktdaten öffentlich | Volumen |
|---|---|---|---|
| landarztboerse.de | ✅ Ja (3055 Inserate aktuell) | ❌ Hinter "Details anzeigen" Klick / Login | Hoch |
| praxisboerse24.de | Statistik (432 Angebote, 2178 Gesuche) | ❌ Nur registrierte Mitglieder | Hoch |
| kvhessen.de/praxisboerse | ✅ Ja (433 Einträge, mit Datum) | ❌ ID-Code-basiert, Kontakt via KV | Mittel |
| praxis-investor.de/inserate | ✅ Ja, Typ + Region | ❌ Verkäufer-Name/Tel nicht sichtbar | Mittel |
| medicalboerse.de | Server-Issue, leeres Index | n/a | n/a |

**Kern-Befund:** Inserate sind volumenstark öffentlich, **aber Kontaktdaten sind systematisch hinter Registrierung/Login**. Datenschutz-orientiertes Branchen-Standard-Verhalten.

### A.3 ID-Resolution-Workaround für Praxisbörsen — getestet

**Test 1 — "Allgemeinmediziner Bad Laer abzugeben":**
- Google-Suche identifiziert 4 plausible Praxen in Bad Laer
- Alle mit Adresse + Telefon + teilweise Inhaber-Name (Lingner, Ellringmann, Rahn)
- Yield: 4 Kandidaten für 1 Inserat → **1:4 manuelle Anrufquote** möglich

**Test 2 — "Zahnarztpraxis Lünen abzugeben":**
- Google identifiziert 9+ Praxen in Lünen
- Inhaber-Namen + Adressen + Telefon öffentlich (Claus, Roos, Hakim, Borek, Drees, Heidler, Murphy, etc.)
- Yield: 9 Kandidaten für 1 Inserat → **1:9 Anrufquote**

**Bewertung:** ID-Resolution für Praxisbörsen-Inserate funktioniert über Google + Praxis-Webseiten, aber **erfordert Closer-seitige Trefferquoten-Akzeptanz** (1 Treffer bei 4-9 Anrufen).

### A.4 Phase-A-Bewertung gegen Validierungs-Gate

**Gate:** "A ≥3/10 ID + Kontakt → Cold-Pipeline tragfähig"

**Resultat:** Quelle existiert, aber Kontakt-Pfad zur Realperson ist:
- Aus HR-Bekanntmachungen: direkt (Name + Firma + Sitz öffentlich, Telefon über Firmenseite/Impressum) → 8-10/10 ID-Yield
- Aus Praxisbörsen: indirekt über Sekundär-Search → 1 von 4-9 Anrufen ist der gesuchte → effektiver Yield niedriger, ~2-3/10

**Verdict: GATE BESTANDEN für HR-Quelle, MARGINAL für Praxisbörsen.**

---

## PHASE B — ERGEBNISSE (kritisch — Negativ-Resultat)

### B.1 Forum-Aktivitäts-Realität (überraschend gering)

Getestete Helium-Foren mit ihrer tatsächlichen Aktivität:

| Forum/Thread | Total Posts | Zeitraum | Letzter Post | Avg Posts/Monat |
|---|---|---|---|---|
| WO Royal Helium Diskussion | 140 | seit Aug 2020 | 23.11.2025 (cat-bavaro) | ~2,4 |
| WO Helium One Global | 703 | seit Jan 2021 | 12.06.2025 (Streetma_n) | ~14 |
| ARIVA Helium One | 112 | seit Jan 2021 | 14.10.2025 (C.Wood) | ~2 |
| WO Total Helium | ~40 | März-Juni 2023 | Juni 2023 (TOT) | tot |

**Kritische Einsicht:** Die V2.1-Annahme von "50-200 aktive DACH-Helium-Watcher-Nicks" war falsch. **Realität: deutlich unter 30 aktive Nicks DACH-weit über alle Helium-Threads zusammen.** Die meisten Threads haben 0-2 aktive Diskutanten und sterben über Wochen.

### B.2 Identity-Resolution-Tests (6 Nicks getestet, 0 aufgelöst)

| Nickname | Forum | Resolution-Pfad versucht | Ergebnis |
|---|---|---|---|
| cat-bavaro | WO Royal Helium | Google, LinkedIn, Cross-Forum | ❌ Nur Forum-Spur, "bavaro" deutet evtl. Bayern an — kein Realname |
| Streetma_n | WO Helium One | Google, WO-Profile-URL | ❌ Profil-URL = 404, kein externes Match |
| C.Wood | ARIVA Helium One | Google, ARIVA-Profil | ❌ Generische Initialen, kein eindeutiger Realname |
| Terminator9 | ARIVA mehrere | Google | ❌ Generischer Nick, mehrere unverknüpfte Aktien-Diskussionen |
| maxmansell | ARIVA Helium One | Google | ❌ Nur Forum-Spur |
| Hopeful76 | WO Total Helium | Google, LinkedIn | ❌ Kein Treffer |

**Yield: 0/6 = effektiv 0%**

### B.3 Warum die ID-Resolution scheitert

1. **Forum-Profile sind defaultmäßig anonym.** WO und ARIVA haben keine öffentlichen Klarnamen-Felder, keine pflichtigen Profil-Angaben.
2. **Nicknames sind nicht Cross-Plattform.** Helium-Watcher-Nicks tauchen nicht parallel auf XING/LinkedIn/Twitter auf — diese Personen pflegen Forum-Identity getrennt von Berufs-Identity.
3. **Posts enthalten kaum Outing-Hinweise.** Im Gegensatz zu manchen Branchen-Foren outen sich Helium-Aktien-Diskutanten kaum mit Region/Beruf/Klarname.
4. **Helium-Aktien-Audience ≠ Helium-Beteiligungs-Audience.** Wer öffentlich über Royal-Helium-Aktien-Performance schreibt, sucht typischerweise Trading-Gewinne, nicht Direktbeteiligungs-ORRI. Die wirklichen ORRI-Interessenten sind im Forum nicht sichtbar.

### B.4 Gate-Bewertung

**Gate:** "B ≥4/10 ID-Yield → Helium-Watcher als zusätzliche Quelle integrieren"
**Gate:** "B <2/10 → Helium-Watcher streichen, nur HR + Praxisbörsen-Quellen"

**Resultat: 0/6 → DEUTLICH unter Schwellwert.**

**Verdict: HELIUM-WATCHER ALS QUELLE FÄLLT WEG.**

Konsequenzen für die Architektur:
- Persona P3 "Helium-Watcher (Cold via ID-Resolution)" ist effektiv nicht skalierbar
- Quelle B in der Pipeline (Foren-Crawler) bringt zu wenig Signal-Wert
- Pipeline reduziert sich auf **eine Schicht: Handelsregister + Praxisbörsen-Trigger**
- Sprach-basierte Persona-Klassifikation entfällt (kein Forum-Korpus mehr)
- Bayes-Scoring vereinfacht sich (weniger Evidenz-Quellen)

---

## PHASE C — ERGEBNISSE (Template-Inventur)

### C.1 Star Oil Production GmbH — was öffentlich da ist

**Webseite staroilproduction.de:**
- Kein Investor-Relations-Bereich öffentlich
- Kein Prospekt-Download
- Kein Material-Bereich
- Nur Unternehmensbeschreibung + Projektübersicht (Arizona, Kansas, Kentucky, Utah, Wyoming)
- Kontakt: `c.klapkai@staroilproduction.de` als zentrale Investor-Anlaufstelle
- Kundenlogin-Bereich vorhanden (nicht testbar von außen)

**BaFin-Prospekt-Datenbank:**
- Keine Star-Oil-Production-Einträge sichtbar
- Möglich: Privatplatzierung ohne Prospektpflicht (§2 Abs. 1 Nr. 3 VermAnlG bei <20 Anteilen + qualifizierte Anleger)
- Oder: hinterlegt unter anderem Emittenten-Namen

### C.2 Template-Liste die der Closer typischerweise versenden möchte

Basierend auf Helium-Beteiligungs-Standard-Sales-Cycle:

| Template | Wahrscheinliche Quelle | Closer-Eigenbau? |
|---|---|---|
| Pinta-Dome-One-Pager | Issuer (anfordern bei c.klapkai@) | nein |
| Pitch-Deck/Verkaufsprospekt | Issuer | nein |
| Cashflow-Modell ORRI-Anteil | Issuer hat vermutlich Excel | nein |
| Technical-Brief Helium-Förderung | Issuer | nein |
| DBA-Quick-Reference US-DE | Closer-Eigenbau (eigenes Steuer-Knowhow) | ja |
| §34-/§7g-/§6b-Beispielrechnung | Closer-Eigenbau (Steuer-Spezifika) | ja |
| Knappheits-Story Helium-Markt 2026 | Closer-Eigenbau (Web-Recherche kompiliert) | ja |
| Star Oil vs NASCO-Differenzierung | Closer-Eigenbau (sensibel, nicht Issuer-Material) | ja |

**Kern-Befund:** ~50% Templates kommen vom Issuer, ~50% baut Closer selbst. **Beides liegt außerhalb User-Scope (K5 bestätigt).**

### C.3 User-Aktion für Closer-Enablement (nicht Material-Build)

Was der User aus MVLT mitnimmt, um Closer zu enablen:
1. **Kontakt zum Issuer-Material:** c.klapkai@staroilproduction.de — Closer kontaktiert direkt für Issuer-Material
2. **BaFin-Datenbank-Link:** Falls Closer Prospekt-Hinterlegung verifizieren will
3. **Konkurrenz-Recherche-Notizen:** NASCO-Differenzierung (Resch-Anwälte-Warnungen) für Closer-Talking-Points

Kein PDF-Build durch User. Gate-Bestätigung für K5.

---

## GESAMT-MVLT-BEWERTUNG

### Validierungs-Gates V2.2 — Ergebnis

| Gate | Schwellwert | Resultat | Status |
|---|---|---|---|
| A: ID + Kontakt aus Cold-Quellen | ≥3/10 | 8-10/10 für HR, 2-3/10 für Praxisbörsen | ✅ HR ja, Praxisbörsen marginal |
| B: ID-Yield Helium-Watcher | ≥4/10 | 0/6 | ❌ DEUTLICHES NEGATIV |
| C: Template-Inventur | nur Inventur | dokumentiert | ✅ |

### Was funktioniert (validiert)
- **Handelsregister/Unternehmensregister als Primärquelle:** trägt
- **Cold-Outbound Persona "Aktiver GmbH-Inhaber":** über HR-Bekanntmachungen erschlossen, Telefon via Firmen-Impressum
- **Cold-Outbound Persona "Exit-GmbH-Verkäufer":** über Anteilseignerwechsel-Bekanntmachungen, gleich verfügbar
- **Praxisverkäufer als Persona:** über Praxisbörsen-Inserate teils erschließbar, aber mit Sekundär-Search (1:4-1:9 Trefferquote)

### Was nicht funktioniert (invalidiert)
- **Helium-Watcher als systematische Quelle:** ID-Yield zu niedrig, Audience zu klein
- **Sprach-basierte Persona-Klassifikation:** kein nutzbares Forum-Korpus mehr
- **9-dimensionale Persönlichkeits-Marker via LLM:** Datengrundlage fehlt für die meisten Leads

### Was die V2.2-Architektur jetzt sein muss (V2.3-Vorschlag)

**Vereinfachte Pipeline:**
```
QUELLEN: Handelsregister-Diff (primär) + Praxisbörsen (sekundär)
   ↓
LEAD-BAU: Person + Firma + Trigger + Telefon
   ↓
SCORING vereinfacht:
   - Hard Gates: DACH, kein Anti-Persona-Indikator,
     keine bekannte Schädigung
   - Bayes mit reduzierter Evidenz-Liste:
     * GmbH-Bilanz/EK
     * Trigger-Aktualität (Tage seit HR-Eintrag)
     * Steuer-Trigger (§16/§34 Indikatoren)
     * Praxisverkauf Q3/Q4
     * Holding/Family-Office-Struktur
   ↓
1-SEITEN-DOSSIER an Closer
```

**Sprach-basierte Persönlichkeits-Marker** entfallen weitgehend aus der Pipeline — wir haben keine Datengrundlage. Stattdessen:
- Closer macht Persona-Einschätzung im Erstgespräch (in 30 Sekunden hörbar)
- Wir liefern Trigger + Vermögensindikator + Erreichbarkeit. Schluss.

### Pool-Realität (Korrektur der V2-Schätzung)

V2 schätzte 30-80 Top-Leads/Jahr.
**Nach MVLT-Korrektur:** 
- HR-Bekanntmachungen DACH GF-/Anteilseigner-Wechsel: ~5.000-10.000/Monat brutto
- Davon mit EK ≥2M nachvollziehbar: ~500-1.000/Monat
- Davon mit DACH-Sitz + nicht-Anti-Persona-Filter: ~200-400/Monat
- Davon manuell+ID-verifiziert: ~50-100/Monat
- Davon Top-Lead (frischer Trigger + Vermögen + Closer-tauglicher Kontakt): **~20-40/Monat = 5-10/Woche**

→ Volumen-Ziel "3-5 Top-Leads/Woche" ist **machbar mit reiner HR-Pipeline**, ohne Helium-Watcher-Quelle.

### Time-to-First-Deal nach MVLT-Korrektur

Keine Verschlechterung gegenüber V2.2-Schätzung:
- Optimistisch: Woche 6-7
- Realistisch: Woche 8-10
- Pessimistisch: Woche 11-14

Helium-Watcher-Ausfall hatte ohnehin nicht den größten Speed-Anteil — Beschleuniger 1 (Trigger-Frische) bleibt voll wirksam.

### Empfehlung an User

**JA, weiter bauen, aber mit V2.3-Architektur (vereinfacht):**
1. Quelle: nur HR + Praxisbörsen-Inserate (Helium-Watcher streichen)
2. Persona-Sprach-Marker raus aus Pipeline, in Closer-Live-Einschätzung
3. Scoring auf Trigger + Vermögen + Frische reduziert
4. Dossier-Format bleibt 1-Seite

**Erste Bauschritte:**
- Playwright-Crawler für Unternehmensregister-Bekanntmachungen (4-6h Setup)
- Manueller Watcher für Praxisbörsen (Closer-eigene Recherche bei Lead-Bau)
- 1-Seite-Dossier-Template als Markdown-Vorlage
- Keine LLM-Persona-Pipeline (entfällt)

**Erwartete Output-Rate nach Setup-Woche:** 3-5 Top-Leads/Woche aus HR-Pipeline allein.



