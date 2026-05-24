"""Tests für Phase 8.2 A1 — Reachability-Engine."""

from __future__ import annotations

import pytest

from helium_pipeline.scoring.reachability import (
    assess_reachability,
    is_direct_line,
    is_persona_email,
)


# ───────────────────────────────────────────────────────────────────────────
# is_persona_email
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("email", [
    "m.mueller@firma.de",
    "max.mustermann@firma.de",
    "mueller-schmidt@firma.de",
    "dr.mueller@firma.de",
    "fischer@firma.de",   # 7 chars, kein Trenner aber lang genug
])
def test_persona_email_positive(email):
    assert is_persona_email(email)


@pytest.mark.parametrize("email", [
    "info@firma.de",
    "kontakt@firma.de",
    "office@firma.de",
    "vertrieb@firma.de",
    "noreply@firma.de",
    "team@firma.de",
    "sales@firma.de",
    "admin@firma.de",
    "buero@firma.de",
])
def test_persona_email_blacklist(email):
    assert not is_persona_email(email)


def test_persona_email_short_no_separator():
    # "ml@firma.de" — 2 chars, kein Trenner → kein persona
    assert not is_persona_email("ml@firma.de")


# ───────────────────────────────────────────────────────────────────────────
# is_direct_line
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("phone", [
    "+49 171 1234567",      # mobile
    "0151 12345678",        # mobile
    "+49 89 1234-567",      # Durchwahl-Trenner
    "030 555-123",          # Durchwahl
])
def test_direct_line_positive(phone):
    assert is_direct_line(phone)


@pytest.mark.parametrize("phone", [
    "+49 89 12345678",      # keine Durchwahl-Trennung
    "030 5550000",          # Zentrale
])
def test_direct_line_negative(phone):
    assert not is_direct_line(phone)


# ───────────────────────────────────────────────────────────────────────────
# assess_reachability — End-to-End
# ───────────────────────────────────────────────────────────────────────────


def test_no_channels_returns_no_data_flag():
    r = assess_reachability(contact_channels=None)
    assert r.no_reachability_data
    assert r.lrs == {}


def test_empty_channels_returns_no_data_flag():
    r = assess_reachability(contact_channels=[])
    assert r.no_reachability_data
    assert r.lrs == {}


def test_inhabergefuehrte_gmbh_full_boost():
    """Kleine GmbH + persona-email + Durchwahl → starkes Reachability."""
    channels = [
        {"channel": "phone", "value": "+49 89 1234-567", "source": "imp"},
        {"channel": "mobile", "value": "+49 171 9876543", "source": "imp"},
        {"channel": "email", "value": "max.mueller@kleine-gmbh.de", "source": "imp"},
    ]
    r = assess_reachability(
        contact_channels=channels,
        company_name="Müller Vermögen GmbH",
        company_size_class="klein",
    )
    assert "reachability_direct_line" in r.lrs
    assert "reachability_personal_email" in r.lrs
    assert "reachability_inhaber_gefuehrt" in r.lrs
    assert "reachability_large_corporate_switchboard" not in r.lrs
    assert r.confidence["direct_line"] >= 1
    assert r.confidence["inhaber_gefuehrt"] >= 2  # size_class + persona_email


def test_konzern_pattern_drücks_reachability():
    """AG mit nur generic-Inboxen → Switchboard-Penalty."""
    channels = [
        {"channel": "phone", "value": "030 5550000", "source": "imp"},
        {"channel": "email", "value": "info@konzern.de", "source": "imp"},
        {"channel": "email", "value": "kontakt@konzern.de", "source": "imp"},
        {"channel": "email", "value": "presse@konzern.de", "source": "imp"},
    ]
    r = assess_reachability(
        contact_channels=channels,
        company_name="Großer Konzern AG",
    )
    assert "reachability_large_corporate_switchboard" in r.lrs
    assert r.lrs["reachability_large_corporate_switchboard"] == 0.5
    # KEIN positives Signal
    assert "reachability_direct_line" not in r.lrs
    assert "reachability_personal_email" not in r.lrs


def test_corporate_AG_but_persona_email_no_penalty():
    """AG mit persona-email → kein Switchboard-Penalty (Widerspruchs-Schutz)."""
    channels = [
        {"channel": "phone", "value": "+49 89 1234-100", "source": "imp"},
        {"channel": "email", "value": "vorstand.mueller@konzern.de", "source": "imp"},
    ]
    r = assess_reachability(
        contact_channels=channels,
        company_name="Beispiel AG",
    )
    assert "reachability_personal_email" in r.lrs
    # AG-Name würde corporate flag setzen, aber positive Signale dabei → kein Penalty
    assert "reachability_large_corporate_switchboard" not in r.lrs


# ───────────────────────────────────────────────────────────────────────────
# Bayes-Integration
# ───────────────────────────────────────────────────────────────────────────


def test_bayes_picks_up_reachability():
    from datetime import date, timedelta
    from uuid import uuid4
    from helium_pipeline.models import (
        BekanntmachungRaw, BekanntmachungType, CompanyEnrichment, CountryCode,
    )
    from helium_pipeline.scoring.bayes import score, ScoringInput

    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Müller Holding GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=800_000)
    channels = [
        {"channel": "mobile", "value": "+49 171 1234567", "source": "imp",
         "confidence": 0.85},
        {"channel": "email", "value": "max.mueller@mh-gmbh.de", "source": "imp"},
    ]
    result = score(ScoringInput(
        bekanntmachung=bek, enrichment=enr,
        contact_channels=channels,
        company_size_class="klein",
    ))
    assert "reachability_direct_line" in result.likelihood_ratios
    assert "reachability_personal_email" in result.likelihood_ratios
    assert result.reachability["confidence_stars"]
    assert not result.reachability["no_reachability_data"]
    # reachability ist eigene Familie im breakdown
    assert "reachability" in result.family_breakdown


def test_bayes_no_reachability_data_flag():
    from datetime import date, timedelta
    from uuid import uuid4
    from helium_pipeline.models import (
        BekanntmachungRaw, BekanntmachungType, CompanyEnrichment, CountryCode,
    )
    from helium_pipeline.scoring.bayes import score, ScoringInput

    bek = BekanntmachungRaw(
        source="t", bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        company_name="Test GmbH",
        bekanntmachung_date=date.today() - timedelta(days=3),
        country_code=CountryCode.DE, crawl_run_id=uuid4(),
    )
    enr = CompanyEnrichment(hrb_nummer="HRB1", equity_eur=800_000)
    result = score(ScoringInput(
        bekanntmachung=bek, enrichment=enr,
        contact_channels=None,
    ))
    assert result.reachability["no_reachability_data"]
    # KEIN reachability-LR
    assert not any(k.startswith("reachability_") for k in result.likelihood_ratios)
