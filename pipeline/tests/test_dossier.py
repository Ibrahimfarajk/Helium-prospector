"""Dossier-Generator Smoke-Tests."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from helium_pipeline.dossier.generator import (
    DossierInput,
    lead_short_id,
    render_dossier,
)
from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    LeadTier,
    PersonInfo,
    ScoreBreakdown,
)


def test_render_basic():
    today = date.today()
    bek = BekanntmachungRaw(
        source="handelsregister.de",
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
        hrb_nummer="HRB 138286",
        register_court="Hamburg",
        company_name="Krause Holding GmbH",
        company_postal_code="80335",
        company_city="München",
        bekanntmachung_date=today - timedelta(days=12),
        crawl_run_id=uuid4(),
    )
    person = PersonInfo(
        first_name="Markus",
        last_name="Krause",
        role="Geschäftsführer",
        appointed_at=today - timedelta(days=12),
    )
    enr = CompanyEnrichment(
        hrb_nummer="HRB 138286",
        equity_eur=3_800_000,
        last_ja_year=2024,
    )
    breakdown = ScoreBreakdown(
        prior=0.001,
        likelihood_ratios={
            "trigger_shareholder_change_0_9mo": 10.0,
            "ek_ge_2m": 8.0,
            "freshness_7_14d": 4.0,
        },
        posterior=0.243,
        tier=LeadTier.T1,
    )
    md = render_dossier(
        DossierInput(
            bekanntmachung=bek,
            person=person,
            enrichment=enr,
            score=breakdown,
            phone="+49 89 123456",
            phone_source="firmen-impressum",
            short_id=lead_short_id(today=today, sequence=3),
            today=today,
        )
    )
    print("\n" + "=" * 70)
    print(md)
    print("=" * 70)
    assert "Krause" in md
    assert "HRB 138286" in md
    # darf nicht doppeltes HRB-Prefix haben
    assert "HRB HRB" not in md
    assert "Posterior" in md
    assert "T1" in md
    assert "0.24" in md or "0.25" in md  # posterior gerundet
    assert "Anteilseignerwechsel" in md
    # 1-Seite-Check: <= ~30 Zeilen
    assert len(md.splitlines()) <= 35, f"Dossier zu lang: {len(md.splitlines())} Zeilen"
