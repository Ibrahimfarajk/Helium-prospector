"""Negative-Features (Phase 8.2 B2).

Pattern-basierte Penalty-Multiplikatoren für Profile die statistisch
KLAR negativ mit Helium-Investment korrelieren.

WICHTIG: Negative LRs werden als Familie "vermoegen" oder "affinitaet"
hinzugefügt, damit Cluster-Cap sie korrekt mit anderen Signalen
gewichtet. Sie werden NICHT als globaler Veto-Filter verwendet —
Bayes bleibt die Source-of-Truth (siehe Variante-I-Entscheidung).

Drei Pattern-Klassen:
- `pure_real_estate_holding`     ×0.3 — reine Immo-Halter
- `dormant_old_holding`          ×0.2 — alt + keine Aktivität
- `law_tax_firm_no_investment`   ×0.3 — Steuerkanzlei/Anwalts-GmbH
"""

from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Pattern-Definitionen
# ───────────────────────────────────────────────────────────────────────────

# Reine Immobilien-Halter — Firmenname-Pattern UND keine Beteiligungs-Aktivität
_REAL_ESTATE_NAME_PATTERN = re.compile(
    r"\b(?:Immobilien|Grundst[üu]cks?|Liegenschafts?|Bautr[äa]ger|"
    r"Wohnungsbau|Bau-?\s?Gesellschaft|Real\s?Estate)\b",
    re.IGNORECASE,
)

# Beteiligungs-Aktivitäts-Indikatoren (im Namen oder raw_text)
_INVESTMENT_ACTIVITY_PATTERN = re.compile(
    r"\b(?:Beteiligung|Investment|Portfolio|Holding|Diversifizier|Sachwert|"
    r"Direkt(?:investment|beteiligung)|Family\s?Office|Asset\s?Management)\b",
    re.IGNORECASE,
)

# Steuerkanzlei / Rechtsanwalts-GmbH-Pattern
_LAW_TAX_FIRM_PATTERN = re.compile(
    r"\b(?:Steuerberatungs?(?:gesellschaft|kanzlei|gmbh)?|"
    r"Wirtschaftspr[üu]fungs?(?:gesellschaft|kanzlei)?|"
    r"Rechtsanw[äa]lt(?:e|s)?(?:gesellschaft|kanzlei|gmbh)?|"
    r"Notar(?:e|iat)?|StB|RA-?GmbH|Anwalts(?:b[üu]ro|gmbh))\b",
    re.IGNORECASE,
)

# Investment-Spuren bei law/tax firms (würde Penalty deaktivieren)
# z.B. "Steuerkanzlei mit Beteiligungs-Spezialisierung" sollte NICHT bestraft werden
_LAW_TAX_HAS_INVESTMENT_HINT = re.compile(
    r"\b(?:Beteiligungs?(?:gesellschaft|berat)|Investment[- ]?(?:berat|spezialis)|"
    r"Sachwert[- ]?(?:berat|invest)|M&A|Corporate\s?Finance)\b",
    re.IGNORECASE,
)


# ───────────────────────────────────────────────────────────────────────────
# Result-Dataclass
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class NegativeFeaturesResult:
    lrs: dict[str, float]
    matched: list[str]  # welche Penalties haben gefeuert
    notes: list[str]


NEGATIVE_LRS = {
    "negative_pure_real_estate_holding": 0.3,
    "negative_dormant_old_holding": 0.2,
    "negative_law_tax_firm_no_investment": 0.3,
}


# ───────────────────────────────────────────────────────────────────────────
# Detection
# ───────────────────────────────────────────────────────────────────────────


def _is_pure_real_estate(
    *, company_name: str, raw_text: str | None
) -> tuple[bool, str]:
    """True wenn Name nach Immo-Halter aussieht UND keine Investment-Aktivität."""
    if not _REAL_ESTATE_NAME_PATTERN.search(company_name):
        return (False, "")

    # Investment-Hint im Namen oder raw_text → kein reiner Halter
    haystack = company_name + " " + (raw_text or "")
    if _INVESTMENT_ACTIVITY_PATTERN.search(haystack):
        return (False, "real_estate_name_but_investment_hint")

    return (True, f"real_estate_name_match: '{company_name}'")


def _is_dormant_old_holding(
    *,
    company_name: str,
    last_ja_year: int | None,
    bekanntmachung_date: date | None,
    today: date,
) -> tuple[bool, str]:
    """True wenn:
    - Name enthält 'Holding' UND
    - last_ja_year > 3 Jahre alt (oder fehlt komplett) UND
    - bekanntmachung > 365 Tage alt (oder fehlt)

    Aktuelle Limitierung: wir haben nur EINEN Bekanntmachung pro Lead im Score,
    nicht die Historie. Wir prüfen also "diese Bekanntmachung ist alt" als Proxy.
    """
    if "holding" not in company_name.lower():
        return (False, "")

    # JA-Veraltung
    ja_stale = (
        last_ja_year is None
        or last_ja_year < today.year - 3
    )

    # Bek-Veraltung (aktuelle Bek wäre frisch — wir messen ob diese alt ist)
    bek_old = (
        bekanntmachung_date is None
        or (today - bekanntmachung_date).days > 365
    )

    if ja_stale and bek_old:
        return (True, f"holding+ja_year={last_ja_year}+bek_age>365d")
    return (False, "")


def _is_law_tax_firm_no_investment(
    *, company_name: str, raw_text: str | None
) -> tuple[bool, str]:
    """True wenn Name nach Kanzlei aussieht UND keine Investment-Aktivität."""
    if not _LAW_TAX_FIRM_PATTERN.search(company_name):
        return (False, "")

    haystack = company_name + " " + (raw_text or "")
    if _LAW_TAX_HAS_INVESTMENT_HINT.search(haystack):
        return (False, "law_tax_firm_but_investment_hint")

    return (True, f"law_tax_firm: '{company_name}'")


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def assess_negative_features(
    *,
    company_name: str,
    raw_text: str | None = None,
    last_ja_year: int | None = None,
    bekanntmachung_date: date | None = None,
    today: date | None = None,
) -> NegativeFeaturesResult:
    """Prüfe alle 3 Negative-Pattern. Returns dict mit gefeuerten LRs.

    Multi-Match: alle gefeuerten Penalties werden hinzugefügt.
    Cluster-Cap entscheidet im Bayes wie sie kombiniert werden (within
    derselben Familie wird stärkstes voll + Rest gedimmt).
    """
    today_d = today or date.today()
    result = NegativeFeaturesResult(lrs={}, matched=[], notes=[])

    is_re, note = _is_pure_real_estate(
        company_name=company_name, raw_text=raw_text
    )
    if is_re:
        result.lrs["negative_pure_real_estate_holding"] = NEGATIVE_LRS[
            "negative_pure_real_estate_holding"
        ]
        result.matched.append("pure_real_estate_holding")
        result.notes.append(note)

    is_dorm, note = _is_dormant_old_holding(
        company_name=company_name,
        last_ja_year=last_ja_year,
        bekanntmachung_date=bekanntmachung_date,
        today=today_d,
    )
    if is_dorm:
        result.lrs["negative_dormant_old_holding"] = NEGATIVE_LRS[
            "negative_dormant_old_holding"
        ]
        result.matched.append("dormant_old_holding")
        result.notes.append(note)

    is_lawtax, note = _is_law_tax_firm_no_investment(
        company_name=company_name, raw_text=raw_text
    )
    if is_lawtax:
        result.lrs["negative_law_tax_firm_no_investment"] = NEGATIVE_LRS[
            "negative_law_tax_firm_no_investment"
        ]
        result.matched.append("law_tax_firm_no_investment")
        result.notes.append(note)

    return result
