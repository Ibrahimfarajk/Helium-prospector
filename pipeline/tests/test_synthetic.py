"""Phase 8.2 A4 — Synthetic-Lead-Generator Tests.

Validiert die 25 Profile aus helium_pipeline.synthetic gegen Bayes-Output.
Bei FAIL: Bayes hat sich verändert ODER Erwartung war falsch — beide
sind worth-investigating.
"""

from __future__ import annotations

import pytest

from helium_pipeline.synthetic import CASES, run_all


def test_all_synthetic_cases_match_expectations():
    """Alle 25 synthetic cases müssen ihre erwarteten Tier+Gold-Werte treffen."""
    result = run_all()
    failed = [c for c in result["cases"] if not c["ok"]]
    if failed:
        msg = "\n".join(
            f"  {c['id']}: expected tier={c['expected_tier']} gold={c['expected_gold']} → "
            f"got tier={c['actual_tier']} gold={c['actual_gold']} reason={c['gold_reason']}"
            for c in failed
        )
        pytest.fail(f"{len(failed)}/{result['summary']['total']} cases failed:\n{msg}")


def test_synthetic_cases_count():
    """Min. 25 Cases, Balance über alle Klassen."""
    assert len(CASES) >= 25
    by_prefix = {}
    for c in CASES:
        prefix = c.id.split("-")[0]
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    assert by_prefix.get("GOLD", 0) >= 5
    assert by_prefix.get("T1", 0) >= 5
    assert by_prefix.get("T2", 0) >= 5
    assert by_prefix.get("T3", 0) >= 5
    assert by_prefix.get("EDGE", 0) >= 5


def test_edge_helium_vv_still_gold():
    """KRITISCH: Echter Helium-Investor mit VV-GmbH muss GOLD bleiben."""
    res = run_all()
    case = next(c for c in res["cases"] if c["id"] == "EDGE-HELIUM-VV")
    assert case["actual_gold"] is True
    assert "helium_direct" in case["gold_reason"]


def test_edge_inhaber_helium_still_gold():
    """KRITISCH: Inhabergeführte Helium-GmbH bleibt Top-Lead."""
    res = run_all()
    case = next(c for c in res["cases"] if c["id"] == "EDGE-INHABER-HELIUM")
    assert case["actual_gold"] is True
    assert case["posterior"] >= 0.50


def test_edge_konzern_ceo_lower_than_helium():
    """Großkonzern-CEO sollte deutlich niedriger als Inhaber-Helium sein."""
    res = run_all()
    konzern = next(c for c in res["cases"] if c["id"] == "EDGE-KONZERN-CEO")
    inhaber = next(c for c in res["cases"] if c["id"] == "EDGE-INHABER-HELIUM")
    assert konzern["posterior"] < inhaber["posterior"]
