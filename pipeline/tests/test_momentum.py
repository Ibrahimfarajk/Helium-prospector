"""Tests für Phase 8.2 B1 — Momentum-Score."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    CountryCode,
)
from helium_pipeline.scoring.bayes import ScoringInput, score
from helium_pipeline.scoring.momentum import compute_momentum_lr


def test_single_trigger_no_momentum():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=10)},
    ]
    lr, count, reason = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert lr is None
    assert count == 1


def test_two_triggers_2x():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=5)},
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=40)},
    ]
    lr, count, _ = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert count == 2
    assert lr == 2.0


def test_three_triggers_3x():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=d)}
        for d in (5, 30, 60)
    ]
    lr, count, _ = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert count == 3
    assert lr == 3.0


def test_cap_at_5_for_many_triggers():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=d)}
        for d in range(1, 90, 5)  # ~18 Triggers
    ]
    lr, count, _ = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert count >= 10
    assert lr == 5.0


def test_outside_window_not_counted():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=5)},
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=120)},  # außerhalb 90d
    ]
    lr, count, _ = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert count == 1
    assert lr is None


def test_different_company_not_counted():
    today = date(2026, 5, 24)
    others = [
        {"hrb_nummer": "HRB1", "company_name": "Test GmbH",
         "bekanntmachung_date": today - timedelta(days=5)},
        {"hrb_nummer": "HRB2", "company_name": "Andere GmbH",
         "bekanntmachung_date": today - timedelta(days=10)},
    ]
    lr, count, _ = compute_momentum_lr(
        hrb_nummer="HRB1", company_name="Test GmbH",
        today=today, other_bekanntmachungen=others,
    )
    assert count == 1


def test_bayes_picks_up_momentum():
    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Aktive GmbH",
        hrb_nummer="HRB99",
        bekanntmachung_date=date.today() - timedelta(days=2),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB99", equity_eur=800_000)
    previous = [
        {"hrb_nummer": "HRB99", "company_name": "Aktive GmbH",
         "bekanntmachung_date": date.today() - timedelta(days=20)},
        {"hrb_nummer": "HRB99", "company_name": "Aktive GmbH",
         "bekanntmachung_date": date.today() - timedelta(days=50)},
    ]
    result = score(ScoringInput(
        bekanntmachung=bek, enrichment=enr,
        previous_bekanntmachungen=previous,
    ))
    assert any(k.startswith("momentum_score_") for k in result.likelihood_ratios)
    # Aktivitäts-Familie sollte momentum enthalten
    assert "aktivitaet" in result.family_breakdown
