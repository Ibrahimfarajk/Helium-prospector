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
from .affinity import (
    check_affinity_signals,
    is_anti_persona_watch_match,
    is_t1_gold,
)
from .anti_filters import (
    address_contains_mailbox_provider,
    is_liquidation_company,
    is_sweet_spot_size,
)
from .bafin_vermittler import is_bafin_vermittler_match
from .momentum import compute_momentum_lr
from .negative_features import NEGATIVE_LRS, assess_negative_features
from .offeneregister import is_mailbox_cluster_address
from .reachability import REACHABILITY_LRS, assess_reachability

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

# ───────────────────────────────────────────────────────────────────────────
# Phase 8.2 — Signal-Familien für Cluster-Cap / Diminishing Returns
# Within-Family: stärkstes LR zählt 100%, weitere mit Gewicht 0.5 (Hybrid).
# Cross-Family: voll multiplikativ.
# Penalty (LR<1) folgt derselben Regel — wird abgeschwächt wenn stärkerer
# Boost in derselben Familie liegt (gewollt: Cashflow-negativ bei sonst-
# starkem Lead soll nicht overkillen).
# ───────────────────────────────────────────────────────────────────────────

FAMILY_VERMOEGEN = "vermoegen"
FAMILY_AKTIVITAET = "aktivitaet"
FAMILY_AFFINITAET = "affinitaet"
FAMILY_REACHABILITY = "reachability"
FAMILY_NEGATIVE = "negative"  # Phase 8.2 B2 — Negative Pattern-Penalties
FAMILY_OTHER = "other"  # uncapped, fully multiplicative

DIMINISHING_WEIGHT = 0.5  # Gewicht für nicht-stärkste LRs in derselben Familie

LR_FAMILY: dict[str, str] = {
    # ─── Vermögen ──────────────────────────────────────────────────────
    "ek_ge_500k": FAMILY_VERMOEGEN,
    "ek_ge_2m": FAMILY_VERMOEGEN,
    "ek_ge_10m": FAMILY_VERMOEGEN,
    "liquid_assets_ge_500k": FAMILY_VERMOEGEN,
    "liquid_assets_ge_1m": FAMILY_VERMOEGEN,
    "liquid_assets_ge_5m": FAMILY_VERMOEGEN,
    "operating_cashflow_ge_200k": FAMILY_VERMOEGEN,
    "operating_cashflow_ge_500k": FAMILY_VERMOEGEN,
    "operating_cashflow_ge_1m": FAMILY_VERMOEGEN,
    "profit_ge_200k": FAMILY_VERMOEGEN,
    "profit_ge_500k": FAMILY_VERMOEGEN,
    "profit_ge_1m": FAMILY_VERMOEGEN,
    "cashflow_negative": FAMILY_VERMOEGEN,
    "liquidity_data_stale": FAMILY_VERMOEGEN,
    # ─── Aktivität ─────────────────────────────────────────────────────
    "freshness_lt_7d": FAMILY_AKTIVITAET,
    "freshness_7_14d": FAMILY_AKTIVITAET,
    "freshness_14_30d": FAMILY_AKTIVITAET,
    "freshness_30_60d": FAMILY_AKTIVITAET,
    "trigger_shareholder_change_0_9mo": FAMILY_AKTIVITAET,
    "trigger_gf_change": FAMILY_AKTIVITAET,
    "trigger_new_registration_holding": FAMILY_AKTIVITAET,
    "trigger_capital_increase": FAMILY_AKTIVITAET,
    "trigger_q3_q4_praxisverkauf": FAMILY_AKTIVITAET,
    "tax_trigger_paragr_16_34": FAMILY_AKTIVITAET,
    # ─── Affinität ─────────────────────────────────────────────────────
    # Investment-affine Persona-Hinweise + Investment-Strukturen
    "name_contains_holding": FAMILY_AFFINITAET,
    "name_contains_beteiligung": FAMILY_AFFINITAET,
    "name_contains_vermoegen": FAMILY_AFFINITAET,
    "name_family_office": FAMILY_AFFINITAET,
    "us_business_hint": FAMILY_AFFINITAET,
    "tax_paragraph_match_ja": FAMILY_AFFINITAET,
    "wphg_voting_rights_3plus": FAMILY_AFFINITAET,
    "wphg_voting_rights_5plus": FAMILY_AFFINITAET,
}


def _family_of(lr_key: str) -> str:
    """Bestimme Familie für einen LR-Key. Dynamische Prefixe für extension."""
    if lr_key.startswith("affinity_"):
        return FAMILY_AFFINITAET
    if lr_key.startswith("reachability_"):
        return FAMILY_REACHABILITY
    if lr_key.startswith("momentum_"):
        return FAMILY_AKTIVITAET
    if lr_key.startswith("negative_"):
        return FAMILY_NEGATIVE
    return LR_FAMILY.get(lr_key, FAMILY_OTHER)


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
    # Vermögen (Bilanz-Eigenkapital)
    "ek_ge_500k": 3.0,
    "ek_ge_2m": 8.0,
    "ek_ge_10m": 15.0,
    # Phase 8.2-B4: Liquiditäts-Daten alt (Bundesanzeiger >= 18 Mo) → dämpfen
    "liquidity_data_stale": 0.5,
    # Phase 6.5-F1: Cashflow-Indikator (echte Liquidität, nicht nur EK-Buchwert)
    "liquid_assets_ge_500k": 4.0,
    "liquid_assets_ge_1m": 8.0,
    "liquid_assets_ge_5m": 15.0,
    "operating_cashflow_ge_200k": 3.0,
    "operating_cashflow_ge_500k": 6.0,
    "operating_cashflow_ge_1m": 10.0,
    "profit_ge_200k": 2.5,
    "profit_ge_500k": 5.0,
    "profit_ge_1m": 8.0,
    "cashflow_negative": 0.5,  # Penalty — Firma verbrennt Cash
    # Phase 6.5-F3: §-Trigger im JA-Volltext (Single-Source via Enrichment)
    "tax_paragraph_match_ja": 25.0,
    # Phase 6.5-F2: Konzern-Cross-Ref (Serien-Unternehmer)
    "wphg_voting_rights_3plus": 8.0,
    "wphg_voting_rights_5plus": 15.0,
    # Persona-Hinweise aus Firmenname / Stammdaten
    "name_contains_beteiligung": 3.0,
    "name_contains_vermoegen": 4.0,
    "name_contains_holding": 4.0,
    "name_family_office": 6.0,
    # Hartes Steuersignal
    "tax_trigger_paragr_16_34": 40.0,
    # US-Affinität (aus Firmenname/Stammdaten — keine Sprach-Analyse mehr in V2.3)
    "us_business_hint": 5.0,
    # Phase 8.2 — Reachability (A1). Familie "reachability".
    **REACHABILITY_LRS,
    # Phase 8.2 — Negative Features (B2). Familie "negative" (eigene Familie
    # damit Penalties nicht durch positive Affinity-LRs gedimmt werden).
    **NEGATIVE_LRS,
}


@dataclass(slots=True)
class ScoringInput:
    bekanntmachung: BekanntmachungRaw
    enrichment: CompanyEnrichment | None = None
    today: date | None = None  # für Test-Reproduzierbarkeit
    # Phase 8.2: Reachability-Input — list of ContactChannel-dicts oder None
    contact_channels: list[dict] | None = None
    impressum_text: str | None = None
    company_size_class: str | None = None
    # Phase 8.2-B1: Vorherige Bekanntmachungen derselben Firma (90-Tage-Fenster)
    # Format: list of {hrb_nummer, company_name, bekanntmachung_date}
    previous_bekanntmachungen: list[dict] | None = None


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

    # Gate 3: Anti-Persona-Watch-List (Konkurrenz/Issuer)
    if is_anti_persona_watch_match(
        company_name=b.company_name, hrb_nummer=b.hrb_nummer
    ):
        reasons.append("watch_list_anti_persona (Konkurrenz/Issuer)")

    # Gate 4: Liquidation-Suffix (Phase 6.5)
    if is_liquidation_company(b.company_name):
        reasons.append("liquidation_suffix")

    # Gate 5: Mailbox-Provider in Adresse (Phase 6.5)
    address = (b.company_address or "") + " " + (b.company_postal_code or "") + " " + (b.company_city or "")
    provider = address_contains_mailbox_provider(address)
    if provider:
        reasons.append(f"mailbox_provider:{provider}")

    # Gate 5b: Briefkasten-Cluster aus OffeneRegister (>100 GmbHs/Adresse)
    is_cluster, count = is_mailbox_cluster_address(b.company_address)
    if is_cluster:
        reasons.append(f"mailbox_cluster:{count}_gmbhs_at_address")

    # Gate 5c: BaFin-Vermittler-Konkurrent
    is_bafin, bafin_cat = is_bafin_vermittler_match(company_name=b.company_name)
    if is_bafin:
        reasons.append(f"bafin_vermittler:{bafin_cat}")

    # Gate 6: Sweet-Spot-Size (nur wenn Enrichment-Daten da)
    if inp.enrichment and (inp.enrichment.balance_sum_eur or inp.enrichment.equity_eur):
        if not is_sweet_spot_size(
            balance_sum_eur=inp.enrichment.balance_sum_eur,
            equity_eur=inp.enrichment.equity_eur,
        ):
            reasons.append("size_not_sweet_spot")

    return (len(reasons) == 0, reasons)


# ───────────────────────────────────────────────────────────────────────────
# Evidenz-Sammlung → LR-Map
# ───────────────────────────────────────────────────────────────────────────


def _collect_evidence(inp: ScoringInput):
    """Sammle alle zutreffenden Evidenzen → (lrs, reachability_result)."""
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

        # Phase 6.5-F1: Cashflow-Indikatoren — höchster Tier wird genommen
        if e.liquid_assets_eur:
            la = e.liquid_assets_eur
            if la >= 5_000_000:
                lrs["liquid_assets_ge_5m"] = LR_TABLE["liquid_assets_ge_5m"]
            elif la >= 1_000_000:
                lrs["liquid_assets_ge_1m"] = LR_TABLE["liquid_assets_ge_1m"]
            elif la >= 500_000:
                lrs["liquid_assets_ge_500k"] = LR_TABLE["liquid_assets_ge_500k"]

        if e.operating_cashflow_eur is not None:
            cf = e.operating_cashflow_eur
            if cf < 0:
                lrs["cashflow_negative"] = LR_TABLE["cashflow_negative"]
            elif cf >= 1_000_000:
                lrs["operating_cashflow_ge_1m"] = LR_TABLE["operating_cashflow_ge_1m"]
            elif cf >= 500_000:
                lrs["operating_cashflow_ge_500k"] = LR_TABLE["operating_cashflow_ge_500k"]
            elif cf >= 200_000:
                lrs["operating_cashflow_ge_200k"] = LR_TABLE["operating_cashflow_ge_200k"]

        if e.profit_eur is not None and e.profit_eur > 0:
            pr = e.profit_eur
            if pr >= 1_000_000:
                lrs["profit_ge_1m"] = LR_TABLE["profit_ge_1m"]
            elif pr >= 500_000:
                lrs["profit_ge_500k"] = LR_TABLE["profit_ge_500k"]
            elif pr >= 200_000:
                lrs["profit_ge_200k"] = LR_TABLE["profit_ge_200k"]

        # Phase 6.5-F3: §-Paragraph-Match im JA-Volltext
        if e.has_paragraph_match:
            lrs["tax_paragraph_match_ja"] = LR_TABLE["tax_paragraph_match_ja"]

        # Phase 6.5-F2: WpHG-Konzern-Cross-Ref (Serien-Unternehmer)
        if e.wphg_voting_rights_count is not None:
            n = e.wphg_voting_rights_count
            if n >= 5:
                lrs["wphg_voting_rights_5plus"] = LR_TABLE["wphg_voting_rights_5plus"]
            elif n >= 3:
                lrs["wphg_voting_rights_3plus"] = LR_TABLE["wphg_voting_rights_3plus"]

    # ─── Affinity-Signals (Phase 6.1) ─────────────────────────────────
    # Pattern-Match + Watch-List + (optional) JA-Volltext-Scan
    ja_text = getattr(e, "ja_text", None) if e else None
    affinity_lrs = check_affinity_signals(
        company_name=b.company_name,
        raw_text=b.raw_text,
        ja_text=ja_text,
        hrb_nummer=b.hrb_nummer,
    )
    lrs.update(affinity_lrs)

    # ─── Reachability (Phase 8.2 A1) ──────────────────────────────────
    reach = assess_reachability(
        contact_channels=inp.contact_channels,
        company_name=b.company_name,
        company_size_class=inp.company_size_class,
        impressum_text=inp.impressum_text,
    )
    lrs.update(reach.lrs)

    # ─── Negative Features (Phase 8.2 B2) ─────────────────────────────
    neg = assess_negative_features(
        company_name=b.company_name,
        raw_text=b.raw_text,
        last_ja_year=e.last_ja_year if e else None,
        bekanntmachung_date=b.bekanntmachung_date,
        today=today,
    )
    lrs.update(neg.lrs)

    # ─── Momentum (Phase 8.2 B1) ──────────────────────────────────────
    if inp.previous_bekanntmachungen:
        m_lr, m_count, m_reason = compute_momentum_lr(
            hrb_nummer=b.hrb_nummer,
            company_name=b.company_name,
            today=today,
            other_bekanntmachungen=inp.previous_bekanntmachungen,
        )
        if m_lr is not None:
            lrs[f"momentum_score_{m_count}_triggers"] = m_lr

    # ─── JA-Stale-Penalty (Phase 8.2 B4) ──────────────────────────────
    # Wenn JA-Daten > 18 Mo alt UND ein Liquiditäts-LR gefeuert hat:
    # dämpfe mit ×0.5 (LR_TABLE["liquidity_data_stale"]).
    # Grund: Liquide Mittel von vor 2 Jahren sind nicht zuverlässig.
    if e and e.last_ja_year is not None:
        years_old = today.year - e.last_ja_year
        ja_stale = years_old >= 2  # 18+ Mo
        liquidity_fired = any(
            k.startswith("liquid_assets_") or k.startswith("operating_cashflow_")
            for k in lrs
        )
        if ja_stale and liquidity_fired:
            lrs["liquidity_data_stale"] = LR_TABLE["liquidity_data_stale"]

    return lrs, reach, neg


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Math (log-odds-Space)
# ───────────────────────────────────────────────────────────────────────────


def _group_by_family(lrs: dict[str, float]) -> dict[str, dict[str, float]]:
    """Gruppiere LRs nach Signal-Familie."""
    grouped: dict[str, dict[str, float]] = {}
    for key, lr in lrs.items():
        fam = _family_of(key)
        grouped.setdefault(fam, {})[key] = lr
    return grouped


def _posterior_from_lrs(
    prior: float, lrs: dict[str, float]
) -> tuple[float, dict[str, dict]]:
    """Berechne Posterior mit Cluster-Cap (Variante A: Hybrid).

    Within-Family: stärkstes LR (=stärkster |log(LR)|) zählt 100%,
    weitere mit Gewicht 0.5 (DIMINISHING_WEIGHT).
    Cross-Family: voll multiplikativ.

    Returns:
        (posterior, family_breakdown) — family_breakdown ist {family: {
            "lrs": {key: lr, ...},
            "strongest_key": str,
            "dimmed_keys": [str, ...],
            "log_odds_contribution": float,
        }} für Audit/UI.
    """
    prior = max(min(prior, 0.999_999), 1e-12)
    log_odds = math.log(prior / (1 - prior))
    breakdown: dict[str, dict] = {}

    grouped = _group_by_family(lrs)
    for fam, family_lrs in grouped.items():
        if fam == FAMILY_OTHER:
            # uncapped: voll multiplikativ
            contribution = 0.0
            for lr in family_lrs.values():
                if lr > 0:
                    contribution += math.log(lr)
            log_odds += contribution
            breakdown[fam] = {
                "lrs": dict(family_lrs),
                "strongest_key": None,
                "dimmed_keys": [],
                "log_odds_contribution": contribution,
            }
            continue

        # Stärkste nach |log(LR)| (größter Effekt egal ob Boost oder Penalty)
        sorted_items = sorted(
            ((k, lr) for k, lr in family_lrs.items() if lr > 0),
            key=lambda kv: abs(math.log(kv[1])),
            reverse=True,
        )
        if not sorted_items:
            continue
        strongest_key, strongest_lr = sorted_items[0]
        contribution = math.log(strongest_lr)
        dimmed_keys = []
        for k, lr in sorted_items[1:]:
            contribution += DIMINISHING_WEIGHT * math.log(lr)
            dimmed_keys.append(k)
        log_odds += contribution
        breakdown[fam] = {
            "lrs": dict(family_lrs),
            "strongest_key": strongest_key,
            "dimmed_keys": dimmed_keys,
            "log_odds_contribution": contribution,
        }

    posterior = 1 / (1 + math.exp(-log_odds))
    return posterior, breakdown


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

    lrs, reach, neg = _collect_evidence(inp)
    posterior, family_breakdown = _posterior_from_lrs(PRIOR, lrs)
    tier = _tier_from_posterior(posterior)

    # T1-GOLD-Label (Phase 6.1 + 8.2-A3 Fat-Tail-Härtung)
    today = inp.today or date.today()
    b = inp.bekanntmachung
    gold, gold_reason, gold_audit = is_t1_gold(
        posterior, lrs,
        bekanntmachung_type=b.bekanntmachung_type,
        company_name=b.company_name,
        days_since_trigger=(today - b.bekanntmachung_date).days,
    )

    return ScoreBreakdown(
        prior=PRIOR,
        likelihood_ratios=lrs,
        posterior=posterior,
        tier=tier if tier else LeadTier.T3,  # nominal — Filter im Pipeline-Step
        hard_gates_passed=True,
        is_gold=gold,
        gold_reason=gold_reason,
        family_breakdown=family_breakdown,
        reachability={
            "confidence_stars": reach.confidence,
            "no_reachability_data": reach.no_reachability_data,
            "notes": reach.notes,
        },
        gold_audit=gold_audit,
        negative_features={
            "matched": neg.matched,
            "notes": neg.notes,
        },
    )


def should_keep(breakdown: ScoreBreakdown) -> bool:
    """True = Lead landet in leads-Tabelle. False = verwerfen."""
    if not breakdown.hard_gates_passed:
        return False
    if breakdown.posterior < T3_THRESHOLD:
        return False
    return True
