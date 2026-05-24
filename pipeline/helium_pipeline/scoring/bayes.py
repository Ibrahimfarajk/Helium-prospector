"""Bayesian Lead-Scoring (V2.3-Architektur).

Modell:
    Prior P(top_lead) = 0.001
    Posterior odds = Prior odds * ∏ LR(evidence_i)
    Posterior probability = sigmoid(log_odds_posterior)

In log-odds space gerechnet für numerische Stabilität.

Hard Gates (KO):
    Gate 1: DACH-Sitz nachweisbar
    Gate 2: Vermögens-Plausibilität (EK ≥500k ODER klarer Liquiditäts-Trigger)

Tier-Einstufung:
    T1  posterior ≥ 0.15
    T2  0.05 ≤ posterior < 0.15
    T3  0.01 ≤ posterior < 0.05
    -   posterior < 0.01 → verworfen
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from ..models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    CountryCode,
    LeadTier,
    ScoreBreakdown,
)

# ───────────────────────────────────────────────────────────────────────────
# Konstanten — alles zentral, leicht anpassbar nach Closer-Feedback
# ───────────────────────────────────────────────────────────────────────────

PRIOR = 0.001

# Tier thresholds
T1_THRESHOLD = 0.15
T2_THRESHOLD = 0.05
T3_THRESHOLD = 0.01

# Vermögens-Schwellen (EUR)
EK_MIN = 500_000.0
EK_TOP = 2_000_000.0
EK_ULTRA = 10_000_000.0

# DACH-PLZ-Pattern (vereinfacht — vollständige Validierung in Crawler)
DACH_COUNTRY_CODES = {CountryCode.DE.value, CountryCode.AT.value, CountryCode.CH.value}

# Likelihood-Ratios — kalibriert nach V2.3-Spec
# (kann später admin-seitig im Web-UI angepasst werden)
LR_TABLE: dict[str, float] = {
    # Trigger-Frische
    "freshness_lt_7d": 5.0,
    "freshness_7_14d": 4.0,
    "freshness_14_30d": 2.0,
    "freshness_30_60d": 1.2,
    # Trigger-Typ
    "trigger_shareholder_change_0_9mo": 10.0,
    "trigger_gf_change": 6.0,
    "trigger_new_registration_holding": 15.0,
    "trigger_capital_increase": 4.0,
    "trigger_q3_q4_praxisverkauf": 8.0,
    # Vermögen
    "ek_ge_500k": 3.0,
    "ek_ge_2m": 8.0,
    "ek_ge_10m": 15.0,
    # Persona-Hinweise aus Firmenname / Stammdaten
    "name_contains_beteiligung": 3.0,
    "name_contains_vermoegen": 4.0,
    "name_contains_holding": 4.0,
    "name_family_office": 6.0,
    # Hartes Steuersignal
    "tax_trigger_paragr_16_34": 40.0,
    # US-Affinität (aus Firmenname/Stammdaten — keine Sprach-Analyse mehr in V2.3)
    "us_business_hint": 5.0,
}


@dataclass(slots=True)
class ScoringInput:
    bekanntmachung: BekanntmachungRaw
    enrichment: CompanyEnrichment | None = None
    today: date | None = None  # für Test-Reproduzierbarkeit


# ───────────────────────────────────────────────────────────────────────────
# Hard Gates
# ───────────────────────────────────────────────────────────────────────────


def _check_hard_gates(inp: ScoringInput) -> tuple[bool, list[str]]:
    """KO-Filter vor Bayes. Returns (passed, list_of_failure_reasons)."""
    reasons: list[str] = []
    b = inp.bekanntmachung

    # Gate 1: DACH
    if b.country_code not in DACH_COUNTRY_CODES:
        reasons.append(f"country_code={b.country_code} nicht DACH")

    # Gate 2: Vermögens-Plausibilität — entweder EK ≥500k oder klarer Trigger
    has_ek = inp.enrichment is not None and (inp.enrichment.equity_eur or 0) >= EK_MIN
    has_clear_trigger = b.bekanntmachung_type in {
        BekanntmachungType.SHAREHOLDER_CHANGE.value,
        BekanntmachungType.NEW_REGISTRATION.value,
        BekanntmachungType.CAPITAL_INCREASE.value,
    }
    if not has_ek and not has_clear_trigger:
        reasons.append(
            "kein EK≥500k UND kein klarer Liquiditäts-Trigger"
        )

    return (len(reasons) == 0, reasons)


# ───────────────────────────────────────────────────────────────────────────
# Evidenz-Sammlung → LR-Map
# ───────────────────────────────────────────────────────────────────────────


def _collect_evidence(inp: ScoringInput) -> dict[str, float]:
    """Sammle alle zutreffenden Evidenzen → {name: lr}."""
    today = inp.today or date.today()
    b = inp.bekanntmachung
    e = inp.enrichment

    lrs: dict[str, float] = {}

    # ─── Trigger-Frische ──────────────────────────────────────────────
    days_since = (today - b.bekanntmachung_date).days
    if days_since < 7:
        lrs["freshness_lt_7d"] = LR_TABLE["freshness_lt_7d"]
    elif days_since < 14:
        lrs["freshness_7_14d"] = LR_TABLE["freshness_7_14d"]
    elif days_since < 30:
        lrs["freshness_14_30d"] = LR_TABLE["freshness_14_30d"]
    elif days_since < 60:
        lrs["freshness_30_60d"] = LR_TABLE["freshness_30_60d"]
    # älter: kein Bonus

    # ─── Trigger-Typ ──────────────────────────────────────────────────
    t = b.bekanntmachung_type
    if t == BekanntmachungType.SHAREHOLDER_CHANGE.value:
        lrs["trigger_shareholder_change_0_9mo"] = LR_TABLE[
            "trigger_shareholder_change_0_9mo"
        ]
    elif t == BekanntmachungType.GF_CHANGE.value:
        lrs["trigger_gf_change"] = LR_TABLE["trigger_gf_change"]
    elif t == BekanntmachungType.NEW_REGISTRATION.value:
        # Boost nur wenn "Holding" / "Beteiligung" / "Vermögen" im Namen → Family-Office-Indikator
        nm = b.company_name.lower()
        if any(kw in nm for kw in ("holding", "beteiligung", "vermögen", "verwaltung")):
            lrs["trigger_new_registration_holding"] = LR_TABLE[
                "trigger_new_registration_holding"
            ]
    elif t == BekanntmachungType.CAPITAL_INCREASE.value:
        lrs["trigger_capital_increase"] = LR_TABLE["trigger_capital_increase"]

    # ─── Vermögens-Stufen ─────────────────────────────────────────────
    if e and e.equity_eur:
        eq = e.equity_eur
        if eq >= EK_ULTRA:
            lrs["ek_ge_10m"] = LR_TABLE["ek_ge_10m"]
        elif eq >= EK_TOP:
            lrs["ek_ge_2m"] = LR_TABLE["ek_ge_2m"]
        elif eq >= EK_MIN:
            lrs["ek_ge_500k"] = LR_TABLE["ek_ge_500k"]

    # ─── Firmen-Name-Soft-Signals ─────────────────────────────────────
    nm_lower = b.company_name.lower()
    if "holding" in nm_lower:
        lrs["name_contains_holding"] = LR_TABLE["name_contains_holding"]
    if "beteiligung" in nm_lower:
        lrs["name_contains_beteiligung"] = LR_TABLE["name_contains_beteiligung"]
    if "vermögen" in nm_lower or "vermogen" in nm_lower:
        lrs["name_contains_vermoegen"] = LR_TABLE["name_contains_vermoegen"]
    if "family office" in nm_lower or "familyoffice" in nm_lower:
        lrs["name_family_office"] = LR_TABLE["name_family_office"]

    # ─── Aus Enrichment ───────────────────────────────────────────────
    if e:
        if e.has_family_office_hint:
            lrs["name_family_office"] = max(
                lrs.get("name_family_office", 0), LR_TABLE["name_family_office"]
            )
        if e.has_us_business_hint:
            lrs["us_business_hint"] = LR_TABLE["us_business_hint"]

    return lrs


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Math (log-odds-Space)
# ───────────────────────────────────────────────────────────────────────────


def _posterior_from_lrs(prior: float, lrs: dict[str, float]) -> float:
    """Berechne Posterior aus Prior + Likelihood-Ratios in log-odds-Space."""
    prior = max(min(prior, 0.999_999), 1e-12)
    log_odds = math.log(prior / (1 - prior))
    for lr in lrs.values():
        if lr > 0:
            log_odds += math.log(lr)
    # sigmoid
    return 1 / (1 + math.exp(-log_odds))


def _tier_from_posterior(posterior: float) -> LeadTier | None:
    if posterior >= T1_THRESHOLD:
        return LeadTier.T1
    if posterior >= T2_THRESHOLD:
        return LeadTier.T2
    if posterior >= T3_THRESHOLD:
        return LeadTier.T3
    return None  # → verwerfen


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def score(inp: ScoringInput) -> ScoreBreakdown:
    """Score einen einzelnen Lead-Kandidaten.

    Returns:
        ScoreBreakdown mit posterior, tier, gates-Status, LR-Map.
        Wenn hard_gates_passed=False oder tier=None → Lead wird verworfen.
    """
    passed, reasons = _check_hard_gates(inp)

    if not passed:
        return ScoreBreakdown(
            prior=PRIOR,
            likelihood_ratios={},
            posterior=0.0,
            tier=LeadTier.T3,  # nominal — wird sowieso verworfen
            hard_gates_passed=False,
            hard_gates_failed_reasons=reasons,
        )

    lrs = _collect_evidence(inp)
    posterior = _posterior_from_lrs(PRIOR, lrs)
    tier = _tier_from_posterior(posterior)

    return ScoreBreakdown(
        prior=PRIOR,
        likelihood_ratios=lrs,
        posterior=posterior,
        tier=tier if tier else LeadTier.T3,  # nominal — Filter im Pipeline-Step
        hard_gates_passed=True,
    )


def should_keep(breakdown: ScoreBreakdown) -> bool:
    """True = Lead landet in leads-Tabelle. False = verwerfen."""
    if not breakdown.hard_gates_passed:
        return False
    if breakdown.posterior < T3_THRESHOLD:
        return False
    return True
