"""Tests für Phase 8.2 B3 — Vorgänger-Fonds-Cross-Match."""

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
from helium_pipeline.scoring.bayes import ScoringInput, score
from helium_pipeline.scoring.predecessor_funds import (
    _name_keys,
    _normalize_name,
    lookup_predecessor_funds,
)

# ───────────────────────────────────────────────────────────────────────────
# Name-Normalisierung
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("inp,expected", [
    ("Müller", "mueller"),
    ("Mueller", "mueller"),
    ("Wölbern", "woelbern"),
    ("Schmidt-Künzel", "schmidt kuenzel"),  # ü→ue
    ("KÖNIG", "koenig"),
    ("Sòltău", "soltau"),
])
def test_normalize_name(inp, expected):
    assert _normalize_name(inp) == expected


def test_name_keys_includes_tokens():
    keys = _name_keys("von der Heyde")
    assert "von der heyde" in keys
    assert "heyde" in keys


# ───────────────────────────────────────────────────────────────────────────
# Lookup
# ───────────────────────────────────────────────────────────────────────────


def test_no_lastname_returns_empty():
    r = lookup_predecessor_funds(person_first_name=None, person_last_name=None)
    assert r.matched_funds == []
    assert r.lr_key is None


def test_no_match_for_random_name():
    r = lookup_predecessor_funds(person_first_name="Hans", person_last_name="Brendlbauer-Fischer")
    assert r.matched_funds == []


def test_wölbern_match():
    """Wölbern Invest — Heinrich Wölbern → 1 Hit, LR=3."""
    r = lookup_predecessor_funds(person_first_name="Heinrich", person_last_name="Wölbern")
    assert "Wölbern Invest" in r.matched_funds
    assert r.lr_key == "affinity_predecessor_fund_1"
    assert r.lr_value == 3.0


def test_wölbern_mueller_variant_match():
    """Schreibvariante: 'Woelbern' soll auch matchen (per name_variants)."""
    r = lookup_predecessor_funds(person_first_name=None, person_last_name="Woelbern")
    assert "Wölbern Invest" in r.matched_funds


def test_soltau_2plus_match():
    """Christoph Soltau ist in Lloyd Fonds + HCI Capital → 2+ Hits, LR=6."""
    r = lookup_predecessor_funds(person_first_name="Christoph", person_last_name="Soltau")
    assert len(r.matched_funds) >= 2
    assert "Lloyd Fonds AG" in r.matched_funds
    assert "HCI Capital" in r.matched_funds
    assert r.lr_key == "affinity_predecessor_fund_2plus"
    assert r.lr_value == 6.0


def test_first_name_initial_filter():
    """Wenn first_name gegeben + nicht-passender Initial → kein Match."""
    # 'Wölbern' ist Heinrich. Wenn wir 'Max Wölbern' suchen, Initial 'M' ≠ 'H' → kein Match
    r = lookup_predecessor_funds(person_first_name="Max", person_last_name="Wölbern")
    assert r.matched_funds == []


def test_first_name_missing_no_filter():
    """Ohne first_name: Match nur über last_name."""
    r = lookup_predecessor_funds(person_first_name=None, person_last_name="Wölbern")
    assert "Wölbern Invest" in r.matched_funds


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Integration
# ───────────────────────────────────────────────────────────────────────────


def test_bayes_picks_up_predecessor_fund():
    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Test GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=800_000)
    result = score(ScoringInput(
        bekanntmachung=bek, enrichment=enr,
        person_first_name="Heinrich",
        person_last_name="Wölbern",
    ))
    assert "affinity_predecessor_fund_1" in result.likelihood_ratios


def test_bayes_no_predecessor_match_normal_name():
    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Test GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=800_000)
    result = score(ScoringInput(
        bekanntmachung=bek, enrichment=enr,
        person_first_name="Max",
        person_last_name="Brendlbauer-Fischer",
    ))
    assert not any(k.startswith("affinity_predecessor_fund_") for k in result.likelihood_ratios)


def test_predecessor_fund_counts_as_affinity_category():
    """B3 muss als Affinity-Kategorie zählen für Multi-Cat-GOLD."""
    from helium_pipeline.scoring.affinity import is_t1_gold

    # Posterior >= T1 + 1 affinity-Hit (predecessor) + 1 affinity-Hit (us) = Multi-Cat
    lrs = {
        "affinity_predecessor_fund_1": 3.0,
        "affinity_us_link": 6.0,
    }
    is_gold, reason, _ = is_t1_gold(0.18, lrs)
    assert is_gold is True
    assert reason.startswith("multi_category_")
