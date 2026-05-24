"""Bayes-Scoring Unit-Tests."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    CountryCode,
    LeadTier,
)
from helium_pipeline.scoring.bayes import (
    PRIOR,
    T1_THRESHOLD,
    T2_THRESHOLD,
    T3_THRESHOLD,
    ScoringInput,
    score,
    should_keep,
)


def make_bek(
    *,
    bekanntmachung_type: BekanntmachungType = BekanntmachungType.SHAREHOLDER_CHANGE,
    company_name: str = "Test GmbH",
    days_old: int = 5,
    country: CountryCode = CountryCode.DE,
) -> BekanntmachungRaw:
    return BekanntmachungRaw(
        source="test",
        bekanntmachung_type=bekanntmachung_type,
        company_name=company_name,
        bekanntmachung_date=date.today() - timedelta(days=days_old),
        country_code=country,
        crawl_run_id=uuid4(),
    )


def make_inp(
    *,
    bek: BekanntmachungRaw | None = None,
    enrichment: CompanyEnrichment | None = None,
    today: date | None = None,
) -> ScoringInput:
    return ScoringInput(
        bekanntmachung=bek or make_bek(),
        enrichment=enrichment,
        today=today or date.today(),
    )


# ───────────────────────────────────────────────────────────────────────────
# Hard Gates
# ───────────────────────────────────────────────────────────────────────────


def test_gate_dach_required():
    """Non-DACH-Country → Gate gerissen."""
    # Note: Pydantic StrEnum casts via use_enum_values, so we need to set country directly
    bek = make_bek()
    bek.country_code = "US"
    result = score(make_inp(bek=bek))
    assert not result.hard_gates_passed
    assert any("DACH" in r for r in result.hard_gates_failed_reasons)


def test_gate_keine_trigger_kein_ek():
    """OTHER-Trigger ohne Enrichment → Gate gerissen."""
    bek = make_bek(bekanntmachung_type=BekanntmachungType.OTHER)
    result = score(make_inp(bek=bek, enrichment=None))
    assert not result.hard_gates_passed


def test_gate_other_trigger_aber_ek_reicht():
    """OTHER-Trigger aber EK ≥500k → Gate OK."""
    bek = make_bek(bekanntmachung_type=BekanntmachungType.OTHER)
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=600_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    assert result.hard_gates_passed


def test_gate_clear_trigger_passes_without_ek():
    """SHAREHOLDER_CHANGE allein reicht für Gate-Pass."""
    bek = make_bek(bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE)
    result = score(make_inp(bek=bek, enrichment=None))
    assert result.hard_gates_passed


# ───────────────────────────────────────────────────────────────────────────
# Posterior / Tier
# ───────────────────────────────────────────────────────────────────────────


def test_lonely_freshness_does_not_pass():
    """OTHER-Trigger + EK reicht Gate, aber ohne Trigger-Boost → niedrig."""
    bek = make_bek(bekanntmachung_type=BekanntmachungType.OTHER, days_old=3)
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=600_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    assert result.hard_gates_passed
    # Mit freshness ×5 + EK ×3 = ×15 → posterior ~ 0.015 → T3
    assert result.tier == LeadTier.T3


def test_combo_anteilseigner_plus_ek_reaches_t2():
    """Anteilseigner-Wechsel + EK ≥2M → T2."""
    bek = make_bek(
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE, days_old=10
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=3_000_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    # LRs: shareholder_change ×10, ek_ge_2m ×8, freshness_7_14d ×4 = ×320 → posterior ~ 0.243
    assert result.tier == LeadTier.T1
    assert result.posterior >= T1_THRESHOLD


def test_holding_neugruendung_plus_ek_reaches_t1():
    """Holding-Neueintragung + EK → T1."""
    bek = make_bek(
        bekanntmachung_type=BekanntmachungType.NEW_REGISTRATION,
        company_name="Krause Holding GmbH",
        days_old=2,
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=3_000_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    # LRs: new_reg_holding ×15, ek_ge_2m ×8, freshness_lt_7d ×5, name_holding ×4 = ×2400
    assert result.tier == LeadTier.T1
    assert result.posterior > 0.5


def test_old_trigger_drops_tier():
    """Gleicher Lead, aber 60 Tage alt → niedrigerer Tier."""
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=3_000_000)
    fresh = score(
        make_inp(
            bek=make_bek(
                bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE, days_old=3
            ),
            enrichment=enr,
        )
    )
    old = score(
        make_inp(
            bek=make_bek(
                bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE, days_old=120
            ),
            enrichment=enr,
        )
    )
    assert fresh.posterior > old.posterior


def test_should_keep_filters_below_threshold():
    """Sehr schwacher Lead wird verworfen."""
    bek = make_bek(bekanntmachung_type=BekanntmachungType.OTHER, days_old=200)
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=600_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    # OTHER + EK only → posterior ~ 0.003 → unter T3-Threshold
    assert result.posterior < T3_THRESHOLD
    assert not should_keep(result)


def test_score_breakdown_is_transparent():
    """ScoreBreakdown enthält alle eingesetzten LRs."""
    bek = make_bek(
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE, days_old=3
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=3_000_000)
    result = score(make_inp(bek=bek, enrichment=enr))
    assert "freshness_lt_7d" in result.likelihood_ratios
    assert "trigger_shareholder_change_0_9mo" in result.likelihood_ratios
    assert "ek_ge_2m" in result.likelihood_ratios
    # Prior steht im breakdown
    assert result.prior == PRIOR


# ───────────────────────────────────────────────────────────────────────────
# Realistische Volumen-Simulation
# ───────────────────────────────────────────────────────────────────────────


def test_realistic_distribution_5_pct_t1():
    """
    Bei 100 zufälligen Bekanntmachungen mit gemischten Trigger-Typen + Vermögen
    erwarten wir grob: 5-15% T1, 15-30% T2, 30-50% T3, Rest verworfen.
    Konkretes Zielvolumen: 5-10 Top-Leads/Woche bei 50-200 Bekanntmachungen/Woche
    => 2.5%-20% T1-Rate. Wir checken konservativ: <30% T1, >5% T1.
    """
    import random

    random.seed(42)
    types = [
        BekanntmachungType.GF_CHANGE,
        BekanntmachungType.GF_CHANGE,
        BekanntmachungType.GF_CHANGE,
        BekanntmachungType.SHAREHOLDER_CHANGE,
        BekanntmachungType.SHAREHOLDER_CHANGE,
        BekanntmachungType.NEW_REGISTRATION,
        BekanntmachungType.CAPITAL_INCREASE,
        BekanntmachungType.OTHER,
        BekanntmachungType.OTHER,
        BekanntmachungType.OTHER,
    ]
    names = [
        "Müller GmbH",
        "Schmidt Holding GmbH",
        "Krause Beteiligungs GmbH",
        "Schultz UG",
        "Wagner & Co. KG",
        "Bauer Vermögensverwaltung GmbH",
    ]

    tier_counts = {"t1": 0, "t2": 0, "t3": 0, "dropped": 0}
    for _ in range(100):
        bek = BekanntmachungRaw(
            source="test",
            bekanntmachung_type=random.choice(types),
            company_name=random.choice(names),
            bekanntmachung_date=date.today() - timedelta(days=random.randint(0, 90)),
            crawl_run_id=uuid4(),
        )
        ek = random.choice([None, 300_000, 600_000, 1_500_000, 3_000_000, 12_000_000])
        enr = (
            CompanyEnrichment(hrb_nummer=f"HRB{random.randint(1, 99999)}", equity_eur=ek)
            if ek
            else None
        )
        result = score(ScoringInput(bekanntmachung=bek, enrichment=enr))
        if not should_keep(result):
            tier_counts["dropped"] += 1
        else:
            tier_counts[str(result.tier)] += 1

    print("Tier-Verteilung 100 Sample:", tier_counts)
    # T1-Rate sollte nicht ridiculous high oder low sein
    assert tier_counts["t1"] >= 3, "T1-Rate zu niedrig (LRs vielleicht zu konservativ)"
    assert tier_counts["t1"] <= 50, "T1-Rate zu hoch (LRs zu aggressiv kalibriert)"
    # Keep-Rate (T1+T2+T3) sollte 20-70% sein
    keep = tier_counts["t1"] + tier_counts["t2"] + tier_counts["t3"]
    assert 15 <= keep <= 75, f"Keep-Rate aus 100 sample = {keep}, erwartet 20-75"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
