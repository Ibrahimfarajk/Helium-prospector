"""Tests für Phase-6.5 Block-2 Filter (BaFin + OffeneRegister + Online + Insolvency)."""

from __future__ import annotations

from helium_pipeline.scoring.bafin_vermittler import is_bafin_vermittler_match
from helium_pipeline.scoring.offeneregister import (
    _normalize_address,
    is_mailbox_cluster_address,
)

# ───────────────────────────────────────────────────────────────────────────
# BaFin-Vermittler
# ───────────────────────────────────────────────────────────────────────────


def test_bafin_match_sachwert_invest():
    m, cat = is_bafin_vermittler_match(company_name="Sachwert Invest GmbH")
    assert m
    assert cat == "sachwert_vermittler"


def test_bafin_match_efonds24():
    m, cat = is_bafin_vermittler_match(company_name="efonds24 AG & Co. KG")
    assert m


def test_bafin_no_match_normal_gmbh():
    m, cat = is_bafin_vermittler_match(company_name="Müller GmbH")
    assert not m


# ───────────────────────────────────────────────────────────────────────────
# OffeneRegister Mailbox-Cluster
# ───────────────────────────────────────────────────────────────────────────


def test_address_normalize_handles_ss_and_mojibake():
    assert "str " in _normalize_address("Friedrichstraße 133") + " "
    assert "str " in _normalize_address("Friedrichstrae 133") + " "
    assert "str " in _normalize_address("Friedrichstr. 133") + " "
    assert "str " in _normalize_address("Hauptstrasse 1") + " "


def test_mailbox_cluster_friedrichstr():
    m, n = is_mailbox_cluster_address("Friedrichstr. 133, 10117 Berlin")
    assert m
    assert n is not None and n >= 100


def test_mailbox_cluster_bavariaring():
    m, n = is_mailbox_cluster_address("Bavariaring 29, 80336 München")
    assert m
    assert n is not None and n >= 1000


def test_no_mailbox_normal_addr():
    m, n = is_mailbox_cluster_address("Hauptstr. 42, 80335 München")
    assert not m


def test_no_mailbox_empty():
    m, n = is_mailbox_cluster_address(None)
    assert not m
    m, n = is_mailbox_cluster_address("")
    assert not m


# ───────────────────────────────────────────────────────────────────────────
# Integration mit Bayes-Hard-Gates
# ───────────────────────────────────────────────────────────────────────────


def test_integration_bafin_blocks_lead():
    from datetime import date, timedelta
    from uuid import uuid4

    from helium_pipeline.models import BekanntmachungRaw, BekanntmachungType, CountryCode
    from helium_pipeline.scoring.bayes import ScoringInput, score

    bek = BekanntmachungRaw(
        source="test",
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Sachwert Invest GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE,
        crawl_run_id=uuid4(),
    )
    result = score(ScoringInput(bekanntmachung=bek))
    assert not result.hard_gates_passed
    assert any("bafin_vermittler" in r for r in result.hard_gates_failed_reasons)


def test_integration_mailbox_cluster_blocks():
    from datetime import date, timedelta
    from uuid import uuid4

    from helium_pipeline.models import BekanntmachungRaw, BekanntmachungType, CountryCode
    from helium_pipeline.scoring.bayes import ScoringInput, score

    bek = BekanntmachungRaw(
        source="test",
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Müller GmbH",
        company_address="Bavariaring 29",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE,
        crawl_run_id=uuid4(),
    )
    result = score(ScoringInput(bekanntmachung=bek))
    assert not result.hard_gates_passed
    assert any("mailbox_cluster" in r for r in result.hard_gates_failed_reasons)
