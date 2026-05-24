"""Tests für Phase 8.2 B5 — Score-Drift-Monitoring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from helium_pipeline.monitoring import (
    RunSnapshot,
    _check_drift,
    compute_run_snapshot,
)


def test_compute_snapshot_basic():
    leads = [
        {"posterior": 0.5, "tier": "t1", "is_gold": True, "gold_reason": "helium_direct_match", "lead_id": "1", "hard_gates_passed": True},
        {"posterior": 0.2, "tier": "t1", "is_gold": False, "lead_id": "2", "hard_gates_passed": True},
        {"posterior": 0.07, "tier": "t2", "is_gold": False, "lead_id": "3", "hard_gates_passed": True},
        {"posterior": 0.0, "tier": None, "is_gold": False, "lead_id": "4", "hard_gates_passed": False},
    ]
    snap = compute_run_snapshot(run_id=uuid4(), scored_leads=leads)
    assert snap.n_scored == 4
    assert snap.n_kept == 3
    assert snap.n_gold == 1
    assert 0.0 < snap.posterior_mean < 1.0
    assert snap.tier_counts == {"t1": 2, "t2": 1}


def test_check_drift_no_baseline():
    snap = RunSnapshot(
        run_id="x", timestamp="t", n_scored=10, n_kept=8, n_gold=2,
        posterior_min=0.01, posterior_max=0.5, posterior_mean=0.15,
        posterior_median=0.12, posterior_p95=0.4,
    )
    # Empty baseline → no alert
    assert _check_drift(snap, []) is None
    # Too small baseline (<3) → no alert
    assert _check_drift(snap, [{"posterior_mean": 0.15}, {"posterior_mean": 0.16}]) is None


def test_check_drift_no_deviation():
    snap = RunSnapshot(
        run_id="x", timestamp="t", n_scored=10, n_kept=8, n_gold=2,
        posterior_min=0.01, posterior_max=0.5, posterior_mean=0.16,
        posterior_median=0.12, posterior_p95=0.4,
    )
    baseline = [
        {"posterior_mean": 0.14}, {"posterior_mean": 0.15},
        {"posterior_mean": 0.16}, {"posterior_mean": 0.17},
    ]
    assert _check_drift(snap, baseline) is None


def test_check_drift_high_deviation():
    """Bei Posterior-Inflation soll Alert kommen."""
    snap = RunSnapshot(
        run_id="x", timestamp="t", n_scored=10, n_kept=8, n_gold=2,
        posterior_min=0.01, posterior_max=0.9, posterior_mean=0.45,
        posterior_median=0.4, posterior_p95=0.8,
    )
    baseline = [
        {"posterior_mean": 0.14}, {"posterior_mean": 0.15},
        {"posterior_mean": 0.16}, {"posterior_mean": 0.17},
    ]
    alert = _check_drift(snap, baseline)
    assert alert is not None
    assert alert["type"] == "posterior_drift"
    assert alert["deviation_sigmas"] > 2.0


def test_record_run_writes_jsonl(tmp_path, monkeypatch):
    """record_run schreibt Snapshot in runs.jsonl."""
    test_file = tmp_path / "runs.jsonl"
    monkeypatch.setattr("helium_pipeline.monitoring._RUNS_LOG", test_file)
    monkeypatch.setattr("helium_pipeline.monitoring._DRIFT_DIR", tmp_path)
    from helium_pipeline.monitoring import record_run

    snap = RunSnapshot(
        run_id="testrun", timestamp="2026-05-24T10:00:00Z",
        n_scored=5, n_kept=3, n_gold=1,
        posterior_min=0.01, posterior_max=0.5, posterior_mean=0.2,
        posterior_median=0.15, posterior_p95=0.45,
    )
    record_run(snap)

    assert test_file.exists()
    lines = test_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["run_id"] == "testrun"
    assert row["n_kept"] == 3
