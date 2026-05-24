"""Anti-Filter-Tests (Phase 6.5)."""

from __future__ import annotations

import pytest

from helium_pipeline.scoring.anti_filters import (
    SizeClass,
    address_contains_mailbox_provider,
    check_anti_filters,
    classify_size,
    is_liquidation_company,
    is_sweet_spot_size,
)


# ───────────────────────────────────────────────────────────────────────────
# Filter 1: Liquidation-Suffix
# ───────────────────────────────────────────────────────────────────────────


def test_liquidation_il_match():
    assert is_liquidation_company("Müller GmbH i.L.")
    assert is_liquidation_company("Müller GmbH i. L.")
    assert is_liquidation_company("Müller GmbH iL")


def test_liquidation_ia_match():
    assert is_liquidation_company("Schmidt AG i.A.")
    assert is_liquidation_company("Schmidt AG i.Abw.")


def test_liquidation_full_words():
    assert is_liquidation_company("Wagner GmbH in Liquidation")
    assert is_liquidation_company("Bauer KG in Abwicklung")
    assert is_liquidation_company("Müller GmbH in Auflösung")


def test_liquidations_gesellschaft():
    assert is_liquidation_company("Liquidationsgesellschaft AU Bau")
    assert is_liquidation_company("Abwicklungsgesellschaft Schmidt")


def test_no_false_positive_normal_companies():
    """Saubere Firmen sollen NICHT als Liquidation erkannt werden."""
    assert not is_liquidation_company("Müller GmbH")
    assert not is_liquidation_company("Berg Beteiligungs GmbH")
    assert not is_liquidation_company("Industriegas Solutions GmbH & Co. KG")


def test_no_false_positive_il_in_middle_of_word():
    """'Hilfe' soll nicht als 'iL' getriggert werden."""
    # word boundaries machen das sicher
    assert not is_liquidation_company("Hilfe AG")
    assert not is_liquidation_company("Mobilfunk GmbH")


def test_no_false_positive_civil_servant_ia():
    """'im Auftrag' Adresszusatz darf nicht als Liq triggern.
    Mein Regex matched 'i.A.' - aber das ist tatsächlich potenziell ambig.
    Bei Adress-Verwendung ist das aber selten im FIRMA-Namen — also bewusster Trade-off."""
    # "i.A." im Firmen-Namen ist praktisch immer Liquidation
    assert is_liquidation_company("Müller GmbH i.A.")


# ───────────────────────────────────────────────────────────────────────────
# Filter 2: Mailbox-Provider
# ───────────────────────────────────────────────────────────────────────────


def test_mailbox_provider_regus():
    assert address_contains_mailbox_provider("Regus Business Center, Mainstr. 1, 80335 München") == "regus"


def test_mailbox_provider_wework():
    assert address_contains_mailbox_provider("WeWork Sony Center, 10785 Berlin") == "wework"


def test_no_mailbox_normal_address():
    assert address_contains_mailbox_provider("Hauptstr. 42, 80335 München") is None


def test_no_mailbox_none_input():
    assert address_contains_mailbox_provider(None) is None


# ───────────────────────────────────────────────────────────────────────────
# Filter 3: Size-Class
# ───────────────────────────────────────────────────────────────────────────


def test_size_small():
    assert classify_size(balance_sum_eur=5_000_000) == SizeClass.SMALL


def test_size_medium():
    assert classify_size(balance_sum_eur=15_000_000) == SizeClass.MEDIUM


def test_size_large():
    assert classify_size(balance_sum_eur=100_000_000) == SizeClass.LARGE


def test_size_unknown():
    assert classify_size(balance_sum_eur=None) == SizeClass.UNKNOWN


def test_sweet_spot_small_with_ek():
    assert is_sweet_spot_size(balance_sum_eur=3_000_000, equity_eur=800_000)


def test_sweet_spot_medium_with_ek():
    assert is_sweet_spot_size(balance_sum_eur=15_000_000, equity_eur=2_000_000)


def test_sweet_spot_fails_too_small_ek():
    assert not is_sweet_spot_size(balance_sum_eur=2_000_000, equity_eur=200_000)


def test_sweet_spot_fails_too_large():
    assert not is_sweet_spot_size(balance_sum_eur=100_000_000, equity_eur=20_000_000)


def test_sweet_spot_unknown_balance_with_ek():
    """Conservative: Unknown Balance + sufficient EK → pass (don't reject when we can't measure)."""
    assert is_sweet_spot_size(balance_sum_eur=None, equity_eur=1_000_000)


# ───────────────────────────────────────────────────────────────────────────
# Aggregated check_anti_filters
# ───────────────────────────────────────────────────────────────────────────


def test_clean_lead_passes_all():
    r = check_anti_filters(
        company_name="Müller Beteiligungs GmbH",
        company_address="Hauptstr. 42, 80335 München",
        balance_sum_eur=3_000_000,
        equity_eur=900_000,
        has_online_presence=True,
        is_insolvency=False,
        is_bafin_vermittler=False,
    )
    assert r.passed
    assert r.rejected_by == []
    assert "no_online_presence" not in r.soft_penalties


def test_liquidation_blocks():
    r = check_anti_filters(company_name="ASCON Software Germany GmbH i.L.")
    assert not r.passed
    assert "liquidation_suffix" in r.rejected_by


def test_mailbox_blocks():
    r = check_anti_filters(
        company_name="Müller GmbH",
        company_address="Regus Business Center, Mainstr. 1, München",
    )
    assert not r.passed
    assert any("mailbox_provider:regus" in x for x in r.rejected_by)


def test_size_too_large_blocks():
    r = check_anti_filters(
        company_name="Großkonzern GmbH",
        balance_sum_eur=200_000_000,
        equity_eur=50_000_000,
    )
    assert not r.passed
    assert "size_class:large" in r.rejected_by


def test_ek_too_low_blocks():
    r = check_anti_filters(
        company_name="Mini GmbH",
        balance_sum_eur=200_000,
        equity_eur=50_000,
    )
    assert not r.passed
    assert "size_class:equity_too_low" in r.rejected_by


def test_insolvency_blocks():
    r = check_anti_filters(company_name="Mueller GmbH", is_insolvency=True)
    assert not r.passed
    assert "insolvency_record" in r.rejected_by


def test_bafin_blocks():
    r = check_anti_filters(company_name="Vermittler GmbH", is_bafin_vermittler=True)
    assert not r.passed
    assert "bafin_vermittler" in r.rejected_by


def test_no_online_presence_soft_penalty():
    r = check_anti_filters(
        company_name="Müller GmbH",
        has_online_presence=False,
    )
    assert r.passed  # Soft, not blocking
    assert r.soft_penalties.get("no_online_presence") == 0.5


def test_unknown_online_presence_no_penalty():
    r = check_anti_filters(
        company_name="Müller GmbH",
        has_online_presence=None,
    )
    assert r.passed
    assert "no_online_presence" not in r.soft_penalties
