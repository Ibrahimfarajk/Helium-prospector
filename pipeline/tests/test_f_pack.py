"""Tests für F1 (Cashflow) + F3 (§-Paragraph) + F2 (Serial-Entrepreneur)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from helium_pipeline.crawlers.bundesanzeiger import (
    extract_liquid_assets_from_ja_text,
    extract_operating_cashflow_from_ja_text,
    extract_paragraph_matches,
    extract_profit_from_ja_text,
)
from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    CountryCode,
)
from helium_pipeline.scoring.bayes import ScoringInput, score

# ───────────────────────────────────────────────────────────────────────────
# F1 — Cashflow-Extraktion
# ───────────────────────────────────────────────────────────────────────────


def test_extract_liquid_assets_basic():
    text = "Kassenbestand, Guthaben bei Kreditinstituten 2.450.000 EUR"
    assert extract_liquid_assets_from_ja_text(text) == 2_450_000.0


def test_extract_liquid_assets_zahlungsmittel():
    text = "Zahlungsmittel und Zahlungsmitteläquivalente 850.000 €"
    assert extract_liquid_assets_from_ja_text(text) == 850_000.0


def test_extract_liquid_assets_teur():
    # TEUR-Tausender-Suffix → Multiplier *1000
    text = "Liquide Mittel 1.250 TEUR"
    assert extract_liquid_assets_from_ja_text(text) == 1_250_000.0


def test_extract_liquid_assets_mio():
    text = "Liquide Mittel 5,2 Mio EUR"
    assert extract_liquid_assets_from_ja_text(text) == 5_200_000.0


def test_extract_liquid_assets_no_match():
    text = "Eigenkapital 1.000.000 EUR"
    assert extract_liquid_assets_from_ja_text(text) is None


def test_extract_operating_cashflow_basic():
    text = "Cashflow aus der laufenden Geschäftstätigkeit 1.250.000 EUR"
    assert extract_operating_cashflow_from_ja_text(text) == 1_250_000.0


def test_extract_operating_cashflow_negative():
    text = "Cashflow aus der laufenden Geschäftstätigkeit -350.000 EUR"
    assert extract_operating_cashflow_from_ja_text(text) == -350_000.0


def test_extract_operating_cashflow_operativ():
    text = "Operativer Cashflow 450.000"
    assert extract_operating_cashflow_from_ja_text(text) == 450_000.0


def test_extract_profit_jahresueberschuss():
    text = "Jahresüberschuss 380.000 EUR"
    assert extract_profit_from_ja_text(text) == 380_000.0


def test_extract_profit_bilanzgewinn():
    text = "Bilanzgewinn 1.200.000"
    assert extract_profit_from_ja_text(text) == 1_200_000.0


def test_extract_profit_jahresfehlbetrag_negative():
    text = "Jahresfehlbetrag 50.000 EUR"
    # Fehlbetrag → negativ
    val = extract_profit_from_ja_text(text)
    assert val is not None and val < 0


# ───────────────────────────────────────────────────────────────────────────
# F3 — §-Paragraph-Match
# ───────────────────────────────────────────────────────────────────────────


def test_paragraph_match_p16():
    text = "Die Veräußerung erfolgte gemäß § 16 Abs. 4 EStG."
    hits = extract_paragraph_matches(text)
    assert "§16 EStG" in hits


def test_paragraph_match_p7g():
    text = "Investitionsabzugsbetrag nach § 7g EStG geltend gemacht."
    hits = extract_paragraph_matches(text)
    assert "§7g EStG" in hits
    assert "IAB §7g" in hits


def test_paragraph_match_veraeusserungsgewinn():
    text = "Der Veräußerungsgewinn wurde steuerneutral übertragen."
    hits = extract_paragraph_matches(text)
    assert "Veräußerungsgewinn" in hits


def test_paragraph_no_match():
    text = "Die Gesellschaft hat im Berichtsjahr Umsatzerlöse erzielt."
    hits = extract_paragraph_matches(text)
    assert hits == []


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Integration F1 + F3
# ───────────────────────────────────────────────────────────────────────────


def _make_bek(name: str = "Test GmbH"):
    return BekanntmachungRaw(
        source="test",
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name=name,
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE,
        crawl_run_id=uuid4(),
    )


def test_bayes_picks_up_liquid_assets():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=1_000_000.0,
        balance_sum_eur=3_000_000.0,
        liquid_assets_eur=2_500_000.0,
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert result.hard_gates_passed
    assert "liquid_assets_ge_1m" in result.likelihood_ratios


def test_bayes_picks_up_operating_cashflow():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=800_000.0,
        balance_sum_eur=2_500_000.0,
        operating_cashflow_eur=750_000.0,
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert result.hard_gates_passed
    assert "operating_cashflow_ge_500k" in result.likelihood_ratios


def test_bayes_cashflow_negative_penalty():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=600_000.0,
        balance_sum_eur=2_000_000.0,
        operating_cashflow_eur=-450_000.0,
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert "cashflow_negative" in result.likelihood_ratios
    assert result.likelihood_ratios["cashflow_negative"] == 0.5


def test_bayes_picks_up_paragraph_match():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=800_000.0,
        balance_sum_eur=2_500_000.0,
        has_paragraph_match=True,
        paragraph_matches=["§16 EStG", "Veräußerungsgewinn"],
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert "tax_paragraph_match_ja" in result.likelihood_ratios
    # §-Match ist LR=25 → muss massiv anschieben
    assert result.posterior > 0.10


def test_bayes_picks_up_wphg_serial():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=800_000.0,
        balance_sum_eur=2_500_000.0,
        wphg_voting_rights_count=4,
        wphg_companies=["Firma A GmbH", "Firma B GmbH", "Firma C AG", "Firma D KG"],
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert "wphg_voting_rights_3plus" in result.likelihood_ratios


def test_bayes_picks_up_wphg_serial_5plus():
    enrichment = CompanyEnrichment(
        hrb_nummer="HRB 12345",
        equity_eur=800_000.0,
        balance_sum_eur=2_500_000.0,
        wphg_voting_rights_count=7,
    )
    result = score(ScoringInput(bekanntmachung=_make_bek(), enrichment=enrichment))
    assert "wphg_voting_rights_5plus" in result.likelihood_ratios
    assert "wphg_voting_rights_3plus" not in result.likelihood_ratios
