"""Mock-Bekanntmachungs-Quelle für End-to-End-Tests.

Generiert realistische deutsche Bekanntmachungs-Einträge basierend auf
echten Mustern (Firmennamen, HRB-Pattern, Bekanntmachungs-Typen).

Genutzt für:
- Phase-2 Test-Lauf (P2.8 Quality-Gate) während handelsregister.de-Crawler
  Production-Tuning bekommt
- CI-Tests ohne Netzwerk-Abhängigkeit
- Demo-Daten für Frontend-Entwicklung in Phase 3

WICHTIG: alle Personen-Namen sind synthetisch (häufige DACH-Nachnamen +
Vornamen kombiniert), keine realen Personen. Firmen-Namen folgen
realistischen DACH-GmbH-Mustern, sind aber fiktiv.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from uuid import UUID

from ..models import BekanntmachungRaw, BekanntmachungType, CountryCode

# ───────────────────────────────────────────────────────────────────────────
# Datensätze für realistische Mock-Generierung
# ───────────────────────────────────────────────────────────────────────────

VORNAMEN = [
    "Markus", "Stefan", "Andreas", "Christian", "Thomas", "Michael",
    "Klaus", "Wolfgang", "Bernd", "Peter", "Jürgen", "Frank",
    "Susanne", "Petra", "Sabine", "Birgit", "Andrea", "Karin",
    "Sebastian", "Florian", "Daniel", "Stephan",
]

NACHNAMEN = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
    "Wagner", "Becker", "Schulz", "Hoffmann", "Schäfer", "Bauer",
    "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann",
    "Krause", "Lehmann", "Hartmann", "König",
]

FIRMENBASIS = [
    "Krause", "Müller", "Berg", "Stein", "Linder", "Hauser",
    "Walter", "Reinhard", "Maier", "Bauer",
]

FIRMENSUFFIXE = [
    "Holding GmbH", "Beteiligungs GmbH", "Vermögensverwaltung GmbH",
    "GmbH & Co. KG", "GmbH", "Verwaltungs GmbH", "Family Office GmbH",
    "Beteiligungsgesellschaft mbH", "Group GmbH",
]

REGISTER_COURTS = [
    "München", "Hamburg", "Frankfurt am Main", "Stuttgart",
    "Düsseldorf", "Köln", "Berlin (Charlottenburg)", "Hannover",
]

CITIES_BY_COURT = {
    "München": ("80331", "München"),
    "Hamburg": ("20095", "Hamburg"),
    "Frankfurt am Main": ("60311", "Frankfurt am Main"),
    "Stuttgart": ("70173", "Stuttgart"),
    "Düsseldorf": ("40213", "Düsseldorf"),
    "Köln": ("50667", "Köln"),
    "Berlin (Charlottenburg)": ("10623", "Berlin"),
    "Hannover": ("30159", "Hannover"),
}

BEKANNTMACHUNGS_VERTEILUNG = [
    # gewichtet wie in der realen Welt: GF_CHANGE häufigster, dann SHAREHOLDER_CHANGE
    (BekanntmachungType.GF_CHANGE, 0.40),
    (BekanntmachungType.SHAREHOLDER_CHANGE, 0.20),
    (BekanntmachungType.NEW_REGISTRATION, 0.15),
    (BekanntmachungType.CAPITAL_INCREASE, 0.10),
    (BekanntmachungType.OTHER, 0.15),
]


def _weighted_choice(weighted: list[tuple]) -> object:
    r = random.random()
    cumulative = 0.0
    for item, weight in weighted:
        cumulative += weight
        if r < cumulative:
            return item
    return weighted[-1][0]


def _format_raw_text(
    *,
    bek_type: BekanntmachungType,
    person_first: str,
    person_last: str,
    company: str,
    hrb: str,
    court: str,
    bek_date: date,
) -> str:
    """Schreibe einen realistischen Bekanntmachungs-Text wie auf handelsregister.de."""
    date_str = bek_date.strftime("%d.%m.%Y")
    base = f"{date_str}\n{court} {hrb}\n{company}\n"

    if bek_type == BekanntmachungType.GF_CHANGE:
        return base + (
            f"Geschäftsführer:\n"
            f"Bestellt als Geschäftsführer: {person_last}, {person_first}, "
            f"einzelvertretungsberechtigt mit der Befugnis, im Namen der "
            f"Gesellschaft mit sich im eigenen Namen oder als Vertreter "
            f"eines Dritten Rechtsgeschäfte abzuschließen."
        )
    if bek_type == BekanntmachungType.SHAREHOLDER_CHANGE:
        return base + (
            f"Veränderung in der Person der Gesellschafter:\n"
            f"Übertragung der Geschäftsanteile durch {person_last}, {person_first}. "
            f"Neuer Anteilseigner: NewCo Holding GmbH, München."
        )
    if bek_type == BekanntmachungType.NEW_REGISTRATION:
        return base + (
            f"Neueintragung\n"
            f"Sitz: {CITIES_BY_COURT.get(court, ('—', '—'))[1]}\n"
            f"Gegenstand: Verwaltung und Verwahrung eigenen Vermögens, "
            f"Beteiligungen an Unternehmen.\n"
            f"Geschäftsführer: {person_last}, {person_first}, "
            f"einzelvertretungsberechtigt."
        )
    if bek_type == BekanntmachungType.CAPITAL_INCREASE:
        return base + (
            f"Kapitalerhöhung:\n"
            f"Das Stammkapital ist um 500.000,00 EUR auf 1.500.000,00 EUR "
            f"erhöht worden. Geschäftsführer: {person_last}, {person_first}."
        )
    return base + f"Sonstige Bekanntmachung. Geschäftsführer: {person_last}, {person_first}."


def generate_mock_bekanntmachungen(
    *,
    crawl_run_id: UUID,
    count: int = 25,
    seed: int = 42,
) -> list[BekanntmachungRaw]:
    """Erzeuge `count` realistische Mock-Bekanntmachungen."""
    random.seed(seed)
    today = date.today()
    items: list[BekanntmachungRaw] = []

    for i in range(count):
        bek_type = _weighted_choice(BEKANNTMACHUNGS_VERTEILUNG)
        court = random.choice(REGISTER_COURTS)
        postal, city = CITIES_BY_COURT[court]
        hrb = f"HRB {random.randint(50000, 250000)}"
        days_ago = random.randint(0, 14)
        bek_date = today - timedelta(days=days_ago)

        first = random.choice(VORNAMEN)
        last = random.choice(NACHNAMEN)
        firmenbasis = random.choice(FIRMENBASIS)
        suffix = random.choice(FIRMENSUFFIXE)
        company = f"{firmenbasis} {suffix}"

        raw_text = _format_raw_text(
            bek_type=bek_type,
            person_first=first,
            person_last=last,
            company=company,
            hrb=hrb,
            court=court,
            bek_date=bek_date,
        )

        bek = BekanntmachungRaw(
            source="mock://realistic_dach",
            bekanntmachung_type=bek_type,
            hrb_nummer=hrb,
            register_court=court,
            company_name=company,
            company_postal_code=postal,
            company_city=city,
            country_code=CountryCode.DE,
            bekanntmachung_date=bek_date,
            raw_text=raw_text,
            parsed_payload={"mock": True, "seed": seed, "index": i},
            crawl_run_id=crawl_run_id,
        )
        items.append(bek)

    return items
