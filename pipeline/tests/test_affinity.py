"""Affinity-Signal-Tests (Phase 6.1)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from helium_pipeline.models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CountryCode,
)
from helium_pipeline.scoring.affinity import (
    check_affinity_signals,
    is_anti_persona_watch_match,
    is_t1_gold,
)
from helium_pipeline.scoring.bayes import ScoringInput, score

# ───────────────────────────────────────────────────────────────────────────
# Helper
# ───────────────────────────────────────────────────────────────────────────


def make_bek(
    *,
    bekanntmachung_type: BekanntmachungType = BekanntmachungType.SHAREHOLDER_CHANGE,
    company_name: str = "Test GmbH",
    days_old: int = 5,
    raw_text: str | None = None,
    hrb: str | None = "HRB 12345",
) -> BekanntmachungRaw:
    return BekanntmachungRaw(
        source="test",
        bekanntmachung_type=bekanntmachung_type,
        hrb_nummer=hrb,
        company_name=company_name,
        bekanntmachung_date=date.today() - timedelta(days=days_old),
        country_code=CountryCode.DE,
        raw_text=raw_text or f"Anteilseignerwechsel HRB {hrb}",
        crawl_run_id=uuid4(),
    )


# ───────────────────────────────────────────────────────────────────────────
# A) Pattern-Match Tests
# ───────────────────────────────────────────────────────────────────────────


def test_helium_direct_match_in_company_name():
    lrs = check_affinity_signals(
        company_name="Helium GmbH",
        raw_text="Anteilseignerwechsel",
        hrb_nummer="HRB 1",
    )
    assert "affinity_helium_direct" in lrs
    assert lrs["affinity_helium_direct"] == 30.0


def test_helium_match_case_insensitive():
    lrs = check_affinity_signals(
        company_name="Edelgas Solutions GmbH",
        hrb_nummer="HRB 2",
    )
    assert "affinity_helium_direct" in lrs


def test_sachwerte_match():
    lrs = check_affinity_signals(
        company_name="Auvesta Edelmetalle AG",
        hrb_nummer=None,
    )
    assert "affinity_sachwerte_konkret" in lrs


def test_us_link_match_state():
    lrs = check_affinity_signals(
        company_name="Texas Energy Group GmbH",
        raw_text="Geschäftsführer-Wechsel in Texas-Standort",
        hrb_nummer=None,
    )
    assert "affinity_us_link" in lrs


def test_tax_struct_match():
    lrs = check_affinity_signals(
        company_name="Müller Family Office GmbH",
        hrb_nummer=None,
    )
    assert "affinity_tax_struct_premium" in lrs


def test_no_false_positive_beteiligung():
    """'Beteiligung' allein sollte NICHT sachwerte triggern (zu breit)."""
    lrs = check_affinity_signals(
        company_name="Müller Beteiligungs GmbH",
        raw_text="Anteilseignerwechsel",
        hrb_nummer=None,
    )
    assert "affinity_sachwerte_konkret" not in lrs


def test_no_false_positive_vermoegen():
    """'Vermögensverwaltung' allein sollte NICHT tax_struct_premium triggern."""
    lrs = check_affinity_signals(
        company_name="Schmidt Vermögensverwaltung GmbH",
        hrb_nummer=None,
    )
    assert "affinity_tax_struct_premium" not in lrs


def test_multi_category_hits():
    """Lead mit Helium + US-Link sollte beide LRs bekommen."""
    lrs = check_affinity_signals(
        company_name="Texas Helium Production LLC",
        hrb_nummer=None,
    )
    affinity_keys = {k for k in lrs if k.startswith("affinity_")}
    # Helium + US-Link mindestens
    assert "affinity_helium_direct" in affinity_keys
    assert "affinity_us_link" in affinity_keys


# ───────────────────────────────────────────────────────────────────────────
# B) JA-Text-Verifizierung
# ───────────────────────────────────────────────────────────────────────────


def test_ja_text_overrides_name_only():
    """Wenn JA-Text Helium-Match hat, ist LR höher (verified-bonus)."""
    lrs = check_affinity_signals(
        company_name="Müller GmbH",
        ja_text="Die Gesellschaft betreibt Industriegas-Lieferungen sowie Helium-Förderung in Texas.",
        hrb_nummer=None,
    )
    # JA-Verified bekommt höheren LR
    assert "affinity_helium_direct_ja_verified" in lrs
    # Name-only-Variante ist überschrieben
    assert "affinity_helium_direct" not in lrs


# ───────────────────────────────────────────────────────────────────────────
# C) Watch-List
# ───────────────────────────────────────────────────────────────────────────


def test_watchlist_match_by_name():
    lrs = check_affinity_signals(
        company_name="Linde plc Deutschland",
        hrb_nummer=None,
    )
    watchlist_keys = [k for k in lrs if k.startswith("affinity_watchlist_")]
    assert len(watchlist_keys) >= 1
    assert lrs[watchlist_keys[0]] == 50.0  # WATCH_LIST_LR


def test_anti_persona_watchlist_blocks_lead():
    """NASCO ist anti_persona=true → Hard-Gate sollte versagen."""
    assert is_anti_persona_watch_match(
        company_name="NASCO Energie & Rohstoff AG",
        hrb_nummer=None,
    )
    # Watchlist-match wird zwar erkannt, aber LR nicht eingefügt
    lrs = check_affinity_signals(
        company_name="NASCO Energie & Rohstoff AG",
        hrb_nummer=None,
    )
    assert not any(k.startswith("affinity_watchlist_") for k in lrs)


def test_anti_persona_passes_through_hard_gate_check():
    """Lead, der in Watch-List anti_persona ist, MUSS Hard-Gate failen."""
    bek = make_bek(
        company_name="NASCO Energie & Rohstoff AG",
        bekanntmachung_type=BekanntmachungType.SHAREHOLDER_CHANGE,
    )
    result = score(ScoringInput(bekanntmachung=bek))
    assert not result.hard_gates_passed
    assert any("anti_persona" in r for r in result.hard_gates_failed_reasons)


# ───────────────────────────────────────────────────────────────────────────
# D) T1-GOLD-Logik (3 Pfade)
# ───────────────────────────────────────────────────────────────────────────


def test_t1_gold_helium_direct():
    """Pfad 1: Helium-Direct-Match → IMMER GOLD bei T1-Posterior."""
    is_gold, reason, _ = is_t1_gold(
        posterior=0.20,
        lrs={"affinity_helium_direct": 30.0, "freshness_lt_7d": 5.0},
    )
    assert is_gold is True
    assert reason == "helium_direct_match"


def test_t1_gold_watchlist():
    """Pfad 1b: Watchlist-Match → GOLD."""
    is_gold, reason, _ = is_t1_gold(
        posterior=0.18,
        lrs={"affinity_watchlist_helium_industry": 50.0},
    )
    assert is_gold is True
    assert reason == "watchlist_match"


def test_t1_gold_high_posterior():
    """Pfad 2: posterior ≥ 0.30 → GOLD ohne Affinity-Hits."""
    is_gold, reason, _ = is_t1_gold(0.35, {"ek_ge_10m": 15.0})
    assert is_gold is True
    assert reason == "high_posterior"


def test_t1_gold_multi_category():
    """Pfad 3: T1 + ≥2 distinct affinity categories."""
    is_gold, reason, _ = is_t1_gold(
        posterior=0.18,
        lrs={
            "affinity_sachwerte_konkret": 12.0,
            "affinity_us_link": 6.0,
        },
    )
    assert is_gold is True
    assert reason.startswith("multi_category_")


def test_t1_gold_single_category_not_enough():
    """Pfad 3 verlangt ≥2 — single category reicht NICHT (außer helium)."""
    is_gold, _, _ = is_t1_gold(
        posterior=0.18,
        lrs={"affinity_us_link": 6.0},
    )
    assert is_gold is False


def test_t1_gold_below_t1_never_gold():
    """Wenn Posterior < T1, niemals GOLD — auch nicht mit Helium-Match."""
    is_gold, _, _ = is_t1_gold(
        posterior=0.05,  # T2
        lrs={"affinity_helium_direct": 30.0},
    )
    assert is_gold is False


def test_ja_verified_counts_for_multi_category():
    """JA-verified-Variante zählt als Kategorie für Multi-Hits."""
    is_gold, _, _ = is_t1_gold(
        posterior=0.18,
        lrs={
            "affinity_sachwerte_konkret_ja_verified": 18.0,
            "affinity_us_link": 6.0,
        },
    )
    assert is_gold is True


# ───────────────────────────────────────────────────────────────────────────
# Phase 8.2 A3: Fat-Tail-Pfad mit affinity_hits>=1-Härtung
# ───────────────────────────────────────────────────────────────────────────


def test_fat_tail_path_vv_gmbh_with_affinity_hit():
    """NEW_REG + VV-Name + freshness<14 + ≥1 affinity → GOLD."""
    is_gold, reason, audit = is_t1_gold(
        posterior=0.16,
        lrs={"affinity_us_link": 6.0, "trigger_new_registration_holding": 15.0},
        bekanntmachung_type="new_registration",
        company_name="Mustermann Vermögensverwaltung GmbH",
        days_since_trigger=5,
    )
    assert is_gold is True
    assert reason.startswith("fat_tail_hardened_")
    assert audit["fat_tail_path_evaluated"]


def test_fat_tail_blocked_without_affinity_hit():
    """Steuerberater-Cluster-Case: VV-GmbH-Gründung OHNE affinity → NICHT GOLD,
    aber A/B-Audit-Flag wird gesetzt für Vergleichsanalyse."""
    is_gold, reason, audit = is_t1_gold(
        posterior=0.16,
        lrs={"trigger_new_registration_holding": 15.0},
        bekanntmachung_type="new_registration",
        company_name="Schmidt Vermögensverwaltung GmbH",
        days_since_trigger=3,
    )
    assert is_gold is False
    assert audit["fat_tail_path_evaluated"]
    assert audit["would_be_gold_without_affinity_filter"]


def test_fat_tail_freshness_too_old():
    """VV-GmbH-Name aber 20 Tage alt → kein Fat-Tail-Pfad."""
    is_gold, _, audit = is_t1_gold(
        posterior=0.16,
        lrs={"affinity_us_link": 6.0},
        bekanntmachung_type="new_registration",
        company_name="Holding XY GmbH",
        days_since_trigger=20,
    )
    assert is_gold is False
    assert not audit["fat_tail_path_evaluated"]


def test_fat_tail_wrong_trigger_type():
    """SHAREHOLDER_CHANGE ist nicht im Fat-Tail-Set."""
    is_gold, _, audit = is_t1_gold(
        posterior=0.16,
        lrs={"affinity_us_link": 6.0},
        bekanntmachung_type="shareholder_change",
        company_name="Holding GmbH",
        days_since_trigger=5,
    )
    assert is_gold is False
    assert not audit["fat_tail_path_evaluated"]


def test_fat_tail_name_pattern_must_match():
    """NEW_REG + Freshness<14 aber 0815-Name → kein Fat-Tail."""
    is_gold, _, audit = is_t1_gold(
        posterior=0.16,
        lrs={"affinity_us_link": 6.0},
        bekanntmachung_type="new_registration",
        company_name="Frische GmbH",
        days_since_trigger=2,
    )
    assert is_gold is False
    assert not audit["fat_tail_path_evaluated"]


# ───────────────────────────────────────────────────────────────────────────
# E) No-Double-Counting (kritisch — User's Bug)
# ───────────────────────────────────────────────────────────────────────────


def test_no_double_counting_beteiligung():
    """Becker-Beispiel: 'Berg Beteiligungs GmbH' soll nur name_contains_beteiligung
    bekommen, NICHT zusätzlich affinity_sachwerte_konkret."""
    bek = make_bek(
        company_name="Berg Beteiligungs GmbH",
        bekanntmachung_type=BekanntmachungType.NEW_REGISTRATION,
        days_old=4,
    )
    result = score(ScoringInput(bekanntmachung=bek))
    # name_contains_beteiligung sollte da sein (weiche LR)
    assert "name_contains_beteiligung" in result.likelihood_ratios
    # affinity_sachwerte_konkret sollte NICHT triggern
    assert "affinity_sachwerte_konkret" not in result.likelihood_ratios


def test_no_double_counting_family_office():
    """'Family Office GmbH' triggert sowohl die weiche LR als auch die affinity-LR.
    Beide sollten unterschiedlich heißen (kein Override)."""
    bek = make_bek(
        company_name="Aequitas Family Office GmbH",
        bekanntmachung_type=BekanntmachungType.NEW_REGISTRATION,
        days_old=4,
    )
    result = score(ScoringInput(bekanntmachung=bek))
    # Beide LRs sollten getrennt sein:
    assert "name_family_office" in result.likelihood_ratios  # weich, ×6
    assert "affinity_tax_struct_premium" in result.likelihood_ratios  # affinity, ×5
    # Score-Test: beide multiplizieren sich = höher als nur eine
    assert result.likelihood_ratios["name_family_office"] == 6.0
    assert result.likelihood_ratios["affinity_tax_struct_premium"] == 5.0


# ───────────────────────────────────────────────────────────────────────────
# F) Realistic Distribution (gegen Mock-Daten)
# ───────────────────────────────────────────────────────────────────────────


def test_realistic_t1_gold_rate_in_random_sample():
    """100 Mock-Bekanntmachungen mit normaler Verteilung → erwartet 0-3% T1-GOLD.
    Bei den existing 13 Mock-Leads erwarten wir 0 T1-GOLD (Mock hat keine
    Helium-/Sachwert-Specifika)."""
    import random
    random.seed(42)
    common_names = [
        "Müller GmbH", "Schmidt Holding GmbH", "Krause Beteiligungs GmbH",
        "Wagner UG", "Bauer Vermögensverwaltung GmbH",
        "Hoffmann KG", "Schäfer GmbH & Co. KG",
    ]
    gold_count = 0
    for _ in range(100):
        bek = make_bek(
            company_name=random.choice(common_names),
            bekanntmachung_type=random.choice([
                BekanntmachungType.SHAREHOLDER_CHANGE,
                BekanntmachungType.NEW_REGISTRATION,
                BekanntmachungType.GF_CHANGE,
            ]),
            days_old=random.randint(0, 30),
        )
        result = score(ScoringInput(bekanntmachung=bek))
        if result.is_gold:
            gold_count += 1
    print(f"GOLD-Rate Mock-Sample: {gold_count}/100")
    assert gold_count <= 5, f"GOLD-Quote zu hoch: {gold_count}/100 — Pattern zu locker?"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
