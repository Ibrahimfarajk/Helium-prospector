"""Vorgänger-Fonds-Cross-Match (Phase 8.2 B3 — STUB).

ZIEL: Personen die in alten Schiffsfonds-/Solar-/Container-Fonds als
Anleger registriert sind, sind statistisch die wahrscheinlichste
Persona für Helium-Direktbeteiligungen (illiquide Sachwerte +
Steueroptimierung + Direkt-Investment-Mindset).

STATUS: STUB. Echte Implementation deferred auf Phase 8.3.

Begründung (B3-Time-Box):
- BaFin-Datenbank ist nur Emittenten-Liste, NICHT Anleger-Liste.
- Anleger-Namen finden sich in alten Fonds-Prospekt-PDFs + Foren
  (anlegerschutz.de, wallstreet-online).
- Sauberer Real-Implementation braucht 4-6h + Discovery der besten
  Quelle. 90-min-Budget war zu knapp.

Architektur-Reservierung jetzt:
- Modul-Slot + Funktions-Signatur + LR-Key vorbereitet
- Im Bayes als Family "affinitaet" geplant (Investment-Mindset-Signal)
- Tests covern Stub-Verhalten (returns None, kein false-positive)

Phase 8.3 Real-Implementation soll:
1. anlegerschutz.de Forum scrape für Anleger-Namen
2. Optionaler PDF-Parse alter Fonds-Prospekte
3. Fuzzy-Name-Match (Levenshtein) gegen Lead-Person-Last-Name
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

log = structlog.get_logger()


PREDECESSOR_FUND_LRS = {
    "affinity_predecessor_fund_1": 3.0,
    "affinity_predecessor_fund_2plus": 6.0,
}


@dataclass(slots=True)
class PredecessorFundResult:
    matched_funds: list[str]  # Fonds-Namen wo Person als Anleger gefunden
    lr_key: str | None
    lr_value: float | None


def lookup_predecessor_funds(
    *,
    person_first_name: str | None,
    person_last_name: str,
) -> PredecessorFundResult:
    """STUB — gibt aktuell immer empty result zurück.

    Phase 8.3 Real: Cross-Match gegen Schiffsfonds-/Solar-/Container-
    Anleger-Listen.

    Sicher: Aktuell None-LR → kein Bayes-Boost.
    Vermutlich: Wird in 8.3 implementiert wenn Datenquelle entschieden.
    Annahme: 5-15% der DACH-HNW-Leads haben mind. 1 Fonds-Hit (Marktdaten
        zeigen ~10% der HNW besitzen oder besessen geschlossene Fonds).
    """
    # TODO Phase 8.3: implement real lookup
    return PredecessorFundResult(
        matched_funds=[],
        lr_key=None,
        lr_value=None,
    )
