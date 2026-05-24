"""Tests für Phase 8.2 B2 — Negative Features."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    CountryCode,
)
from helium_pipeline.scoring.bayes import score, ScoringInput
from helium_pipeline.scoring.negative_features import assess_negative_features


# ───────────────────────────────────────────────────────────────────────────
# pure_real_estate_holding
# ───────────────────────────────────────────────────────────────────────────


def test_pure_real_estate_matches():
    r = assess_negative_features(company_name="Müller Immobilien GmbH")
    assert "negative_pure_real_estate_holding" in r.lrs
    assert "pure_real_estate_holding" in r.matched


def test_real_estate_with_investment_hint_no_penalty():
    r = assess_negative_features(
        company_name="Müller Immobilien Holding GmbH",
        raw_text="Beteiligungs- und Investmentgesellschaft",
    )
    assert "negative_pure_real_estate_holding" not in r.lrs


def test_grundstuecks_gmbh_matches():
    r = assess_negative_features(company_name="ABC Grundstücks GmbH")
    assert "negative_pure_real_estate_holding" in r.lrs


# ───────────────────────────────────────────────────────────────────────────
# dormant_old_holding
# ───────────────────────────────────────────────────────────────────────────


def test_dormant_old_holding_with_stale_ja():
    today = date(2026, 5, 24)
    r = assess_negative_features(
        company_name="X Holding GmbH",
        last_ja_year=2020,  # 6 Jahre alt
        bekanntmachung_date=today - timedelta(days=400),
        today=today,
    )
    assert "negative_dormant_old_holding" in r.lrs


def test_dormant_recent_ja_no_penalty():
    today = date(2026, 5, 24)
    r = assess_negative_features(
        company_name="X Holding GmbH",
        last_ja_year=2024,
        bekanntmachung_date=today - timedelta(days=400),
        today=today,
    )
    assert "negative_dormant_old_holding" not in r.lrs


def test_dormant_no_holding_name_no_penalty():
    today = date(2026, 5, 24)
    r = assess_negative_features(
        company_name="Industrie GmbH",
        last_ja_year=2018,
        bekanntmachung_date=today - timedelta(days=500),
        today=today,
    )
    assert "negative_dormant_old_holding" not in r.lrs


# ───────────────────────────────────────────────────────────────────────────
# law_tax_firm_no_investment
# ───────────────────────────────────────────────────────────────────────────


def test_steuerberatung_matches():
    r = assess_negative_features(company_name="Schmidt Steuerberatungsgesellschaft mbH")
    assert "negative_law_tax_firm_no_investment" in r.lrs


def test_rechtsanwalts_gmbh_matches():
    r = assess_negative_features(company_name="Müller Rechtsanwälte GmbH")
    assert "negative_law_tax_firm_no_investment" in r.lrs


def test_wirtschaftspruefer_matches():
    r = assess_negative_features(company_name="ABC Wirtschaftsprüfungsgesellschaft")
    assert "negative_law_tax_firm_no_investment" in r.lrs


def test_steuerberatung_with_investment_focus_no_penalty():
    r = assess_negative_features(
        company_name="Steuerberatung mit M&A-Spezialisierung GmbH",
        raw_text="Corporate Finance und Beteiligungsberatung",
    )
    assert "negative_law_tax_firm_no_investment" not in r.lrs


def test_normal_gmbh_no_penalty():
    r = assess_negative_features(company_name="Industrie GmbH")
    assert r.lrs == {}
    assert r.matched == []


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Integration — Steuerberater-VV-GmbH wird jetzt sauber gefiltert
# ───────────────────────────────────────────────────────────────────────────


def test_steuerberater_vv_with_negative_filter():
    """B2 Negative-Feature drückt Steuerberatungs-GmbH-Score korrekt."""
    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.NEW_REGISTRATION,
        company_name="Schmidt Steuerberatung GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    # Vermögensindikator triggers Gates: EK 600k
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=600_000)
    result = score(ScoringInput(bekanntmachung=bek, enrichment=enr))
    assert "negative_law_tax_firm_no_investment" in result.likelihood_ratios
    assert "law_tax_firm_no_investment" in result.negative_features["matched"]


def test_real_estate_holding_penalty_drops_posterior():
    """Reine Immo-Halter werden gegenüber Investment-Holding sauber bestraft."""
    bek_pure = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Schmidt Immobilien GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    bek_inv = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Schmidt Investment GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=2_000_000)
    r_pure = score(ScoringInput(bekanntmachung=bek_pure, enrichment=enr))
    r_inv = score(ScoringInput(bekanntmachung=bek_inv, enrichment=enr))
    # Pure Immo sollte deutlich niedrigeren Posterior haben
    assert r_pure.posterior < r_inv.posterior
    assert "negative_pure_real_estate_holding" in r_pure.likelihood_ratios
