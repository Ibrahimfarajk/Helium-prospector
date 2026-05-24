"""Tests für Phase 8.2-P1 — rescore-CLI Helpers.

Property-Test: bei statischen LRs erzeugt _reconstruct_enrichment_from_lrs
ein Enrichment das beim Re-Score wieder dieselben (oder höhere) LRs feuert.

Damit ist garantiert: rescore-CLI degradiert KEINE legit Leads stillschweigend
wenn Bayes-Logik in Zukunft erweitert wird.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from helium_pipeline.main import _reconstruct_enrichment_from_lrs
from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CountryCode,
)
from helium_pipeline.scoring.bayes import score, ScoringInput


def _make_bek(name: str = "Test GmbH", btype=BekanntmachungType.SHAREHOLDER_CHANGE):
    return BekanntmachungRaw(
        source="rescore-test",
        bekanntmachung_type=btype,
        company_name=name,
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE,
        crawl_run_id=uuid4(),
    )


# ───────────────────────────────────────────────────────────────────────────
# Property-Tests: Reconstruct → Re-Score → LR-Identität
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lr_key,expected_field,min_value", [
    ("ek_ge_500k", "equity_eur", 500_000.0),
    ("ek_ge_2m", "equity_eur", 2_000_000.0),
    ("ek_ge_10m", "equity_eur", 10_000_000.0),
    ("liquid_assets_ge_500k", "liquid_assets_eur", 500_000.0),
    ("liquid_assets_ge_1m", "liquid_assets_eur", 1_000_000.0),
    ("liquid_assets_ge_5m", "liquid_assets_eur", 5_000_000.0),
    ("operating_cashflow_ge_200k", "operating_cashflow_eur", 200_000.0),
    ("operating_cashflow_ge_500k", "operating_cashflow_eur", 500_000.0),
    ("operating_cashflow_ge_1m", "operating_cashflow_eur", 1_000_000.0),
    ("profit_ge_200k", "profit_eur", 200_000.0),
    ("profit_ge_500k", "profit_eur", 500_000.0),
    ("profit_ge_1m", "profit_eur", 1_000_000.0),
])
def test_reconstruct_threshold_sets_lower_bound(lr_key, expected_field, min_value):
    """Wenn alter LR feuerte, soll Reconstruct den Wert auf untere Schwelle setzen."""
    old_lrs = {lr_key: 1.0}  # value irrelevant, key triggert reconstruct
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    actual = getattr(enr, expected_field)
    assert actual == min_value, f"{lr_key} should set {expected_field} to {min_value}, got {actual}"


def test_reconstruct_higher_threshold_wins():
    """Bei mehreren ek_-LRs gewinnt der höchste."""
    old_lrs = {"ek_ge_500k": 3.0, "ek_ge_2m": 8.0, "ek_ge_10m": 15.0}
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    assert enr.equity_eur == 10_000_000.0


def test_reconstruct_cashflow_negative():
    """cashflow_negative-LR setzt operating_cashflow_eur < 0."""
    old_lrs = {"cashflow_negative": 0.5}
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    assert enr.operating_cashflow_eur is not None
    assert enr.operating_cashflow_eur < 0


def test_reconstruct_paragraph_match():
    """tax_paragraph_match_ja-LR setzt has_paragraph_match=True."""
    old_lrs = {"tax_paragraph_match_ja": 25.0}
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    assert enr.has_paragraph_match is True


def test_reconstruct_wphg_count():
    """wphg_voting_rights_5plus setzt count=5."""
    old_lrs = {"wphg_voting_rights_5plus": 15.0}
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    assert enr.wphg_voting_rights_count == 5


def test_reconstruct_stale_ja_marker():
    """liquidity_data_stale → last_ja_year wird auf alt gesetzt (3 Jahre zurück)."""
    old_lrs = {
        "liquidity_data_stale": 0.5,
        "liquid_assets_ge_1m": 8.0,
    }
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs=old_lrs, today_year=2026
    )
    assert enr.last_ja_year == 2023  # today-3


def test_reconstruct_no_lrs_empty_enrichment():
    """Leere LRs → minimal-Enrichment ohne Werte."""
    enr = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X", old_lrs={}, today_year=2026
    )
    assert enr.hrb_nummer == "HRB X"
    assert enr.equity_eur is None
    assert enr.liquid_assets_eur is None


# ───────────────────────────────────────────────────────────────────────────
# End-to-End-Property: Original-Score → Reconstruct → Re-Score → Tier-Stabilität
# ───────────────────────────────────────────────────────────────────────────


def test_roundtrip_tier_stable_for_full_enrichment():
    """Property: score → extract LRs → reconstruct → re-score: Tier bleibt gleich."""
    from helium_pipeline.models import CompanyEnrichment

    bek = _make_bek("Müller Holding GmbH")
    enr_original = CompanyEnrichment(
        hrb_nummer="HRB X",
        equity_eur=3_000_000,
        liquid_assets_eur=1_500_000,
        operating_cashflow_eur=600_000,
        profit_eur=400_000,
        last_ja_year=2024,
        has_paragraph_match=True,
        wphg_voting_rights_count=4,
    )
    # Original-Score
    sb_orig = score(ScoringInput(bekanntmachung=bek, enrichment=enr_original))
    # Reconstruct + Re-Score
    enr_rec = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X",
        old_lrs=sb_orig.likelihood_ratios,
        today_year=date.today().year,
    )
    sb_rescored = score(ScoringInput(bekanntmachung=bek, enrichment=enr_rec))

    # Tier muss erhalten bleiben
    assert sb_rescored.tier == sb_orig.tier, (
        f"Tier-Drift: orig={sb_orig.tier} → rescored={sb_rescored.tier}\n"
        f"orig_lrs={sb_orig.likelihood_ratios}\n"
        f"rescored_lrs={sb_rescored.likelihood_ratios}"
    )


def test_roundtrip_gold_stable_for_high_affinity():
    """GOLD-Lead mit Helium-Pattern bleibt GOLD nach Rescore."""
    from helium_pipeline.models import CompanyEnrichment

    bek = _make_bek("Helium Capital Holding GmbH")
    enr = CompanyEnrichment(hrb_nummer="HRB X", equity_eur=2_500_000)
    sb_orig = score(ScoringInput(bekanntmachung=bek, enrichment=enr))
    assert sb_orig.is_gold is True

    enr_rec = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X",
        old_lrs=sb_orig.likelihood_ratios,
        today_year=date.today().year,
    )
    sb_rescored = score(ScoringInput(bekanntmachung=bek, enrichment=enr_rec))
    assert sb_rescored.is_gold is True
    assert sb_rescored.gold_reason == sb_orig.gold_reason


def test_roundtrip_posterior_close_enough():
    """Property: Posterior nach Rescore ist nahe am Original (innerhalb 20%-Spanne).

    Untere-Schwellen-Reconstruction ist konservativ → Re-Score-Posterior
    kann LEICHT niedriger sein, aber nicht dramatisch."""
    from helium_pipeline.models import CompanyEnrichment

    bek = _make_bek("Solid Holding GmbH")
    enr = CompanyEnrichment(
        hrb_nummer="HRB X",
        equity_eur=4_500_000,  # ek_ge_2m feuert
        liquid_assets_eur=2_500_000,  # liquid_assets_ge_1m
    )
    sb_orig = score(ScoringInput(bekanntmachung=bek, enrichment=enr))
    enr_rec = _reconstruct_enrichment_from_lrs(
        hrb_nummer="HRB X",
        old_lrs=sb_orig.likelihood_ratios,
        today_year=date.today().year,
    )
    sb_rescored = score(ScoringInput(bekanntmachung=bek, enrichment=enr_rec))

    # Posterior-Drift soll < 20% absolut sein
    drift = abs(sb_rescored.posterior - sb_orig.posterior)
    assert drift < 0.20, (
        f"Posterior-Drift zu groß: orig={sb_orig.posterior:.4f} "
        f"rescored={sb_rescored.posterior:.4f} drift={drift:.4f}"
    )
