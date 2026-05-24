"""Score-Drift-Monitoring (Phase 8.2 B5 + P2).

Persistence: Supabase-Tabelle `drift_snapshots` (Phase 8.2-P2).
Local-JSONL ist nur Fallback wenn kein Repo verfügbar (Tests, dry-run).

Architektur:
- Posterior-Snapshot pro Cron-Run (FULL + DELTA)
- Pro-Run-Statistik (min/max/mean/median/p95/posterior_count + tier-counts)
- 7-Tage-Baseline aus letzten 7 Snapshots (DB-side query)
- Alert wenn aktueller mean um ≥2σ vom Baseline-Mean abweicht
- Stichprobe: 3 zufällige GOLD-Leads pro Run ins Log

Discord-Alert: nach 7 Tagen Real-Daten scharf geschaltet (siehe TODO unten).
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger()


_DRIFT_DIR = Path.home() / ".helium-pipeline" / "drift"
_DRIFT_DIR.mkdir(parents=True, exist_ok=True)
_RUNS_LOG = _DRIFT_DIR / "runs.jsonl"  # Local-Fallback (Tests / dry-run)

_BASELINE_WINDOW = 7  # Runs
_ALERT_SIGMAS = 2.0
_GOLD_SAMPLE_SIZE = 3


@dataclass(slots=True)
class RunSnapshot:
    """Posterior-Verteilung eines Cron-Runs."""

    run_id: str
    timestamp: str
    n_scored: int
    n_kept: int  # passed hard-gates AND tier!=None
    n_gold: int
    posterior_min: float
    posterior_max: float
    posterior_mean: float
    posterior_median: float
    posterior_p95: float
    tier_counts: dict[str, int] = field(default_factory=dict)
    gold_sample_ids: list[str] = field(default_factory=list)
    gold_sample_reasons: list[str] = field(default_factory=list)
    alert: dict | None = None  # populated bei drift


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(round(0.95 * (len(s) - 1))))
    return s[idx]


def compute_run_snapshot(
    *,
    run_id: UUID | str,
    scored_leads: list[dict],
) -> RunSnapshot:
    """Berechne Drift-Snapshot eines Runs.

    Args:
        scored_leads: list of dicts mit {posterior, tier, is_gold, gold_reason, lead_id}.
            Sollte ALLE gescorten Leads enthalten (auch verworfene), damit Distribution stimmt.
    """
    posteriors = [l["posterior"] for l in scored_leads if l.get("posterior") is not None]
    kept = [l for l in scored_leads if l.get("tier") and l.get("hard_gates_passed", True)]
    gold = [l for l in kept if l.get("is_gold")]

    tier_counts: dict[str, int] = {}
    for l in kept:
        t = l.get("tier")
        if t:
            tier_counts[t] = tier_counts.get(t, 0) + 1

    sample = random.sample(gold, min(_GOLD_SAMPLE_SIZE, len(gold))) if gold else []

    snap = RunSnapshot(
        run_id=str(run_id),
        timestamp=datetime.now(UTC).isoformat(),
        n_scored=len(scored_leads),
        n_kept=len(kept),
        n_gold=len(gold),
        posterior_min=min(posteriors) if posteriors else 0.0,
        posterior_max=max(posteriors) if posteriors else 0.0,
        posterior_mean=statistics.fmean(posteriors) if posteriors else 0.0,
        posterior_median=statistics.median(posteriors) if posteriors else 0.0,
        posterior_p95=_p95(posteriors),
        tier_counts=tier_counts,
        gold_sample_ids=[str(l.get("lead_id", "")) for l in sample],
        gold_sample_reasons=[l.get("gold_reason", "") for l in sample],
    )
    return snap


def _load_baseline_local(window: int = _BASELINE_WINDOW) -> list[dict]:
    """Fallback: lade letzte N Snapshots aus Local-JSONL (Tests/Dry-Run)."""
    if not _RUNS_LOG.exists():
        return []
    rows = []
    with _RUNS_LOG.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows[-window:]


def _check_drift(snap: RunSnapshot, baseline: list[dict]) -> dict | None:
    """Vergleiche Snap mit Baseline. Returns alert-dict wenn Drift detected.

    Aktuell INFO-only. Echter Alert (Discord/Email) kommt nach 7 Tagen
    Real-Daten."""
    if len(baseline) < 3:
        return None  # zu wenig Datenpunkte

    base_means = [b["posterior_mean"] for b in baseline if "posterior_mean" in b]
    if not base_means:
        return None

    base_mean = statistics.fmean(base_means)
    base_std = statistics.stdev(base_means) if len(base_means) >= 2 else 0.0
    current = snap.posterior_mean

    if base_std == 0:
        return None
    deviation = (current - base_mean) / base_std

    if abs(deviation) >= _ALERT_SIGMAS:
        return {
            "type": "posterior_drift",
            "deviation_sigmas": round(deviation, 2),
            "baseline_mean": round(base_mean, 4),
            "current_mean": round(current, 4),
            "baseline_window": len(base_means),
            "severity": "high" if abs(deviation) > 3 else "medium",
        }
    return None


def record_run(snap: RunSnapshot, *, repo: Any = None) -> None:
    """Persist snapshot. Checke Drift gegen Baseline.

    Args:
        snap: berechneter Snapshot.
        repo: SupabaseRepo wenn DB-Persistence gewünscht (Production).
            Falls None: Fallback auf Local-JSONL (Tests/Dry-Run).
    """
    # Baseline aus DB bevorzugt, sonst local
    baseline: list[dict] = []
    if repo is not None:
        try:
            baseline = repo.fetch_recent_drift_snapshots(limit=_BASELINE_WINDOW)
        except Exception as e:
            log.warning("drift_baseline_db_fail", error=str(e))
            baseline = []
    if not baseline:
        baseline = _load_baseline_local()

    snap.alert = _check_drift(snap, baseline)

    if snap.alert:
        log.warning(
            "score_drift_alert",
            run_id=snap.run_id,
            deviation_sigmas=snap.alert["deviation_sigmas"],
            baseline_mean=snap.alert["baseline_mean"],
            current_mean=snap.alert["current_mean"],
        )
        # TODO Phase 8.3: Discord-Webhook scharf schalten nach 7d Real-Daten.

    log.info(
        "score_drift_snapshot",
        run_id=snap.run_id,
        n_kept=snap.n_kept,
        n_gold=snap.n_gold,
        posterior_mean=round(snap.posterior_mean, 4),
        posterior_p95=round(snap.posterior_p95, 4),
        tier_counts=snap.tier_counts,
        alert=snap.alert,
    )

    row = {
        "run_id": snap.run_id,
        "timestamp": snap.timestamp,
        "n_scored": snap.n_scored,
        "n_kept": snap.n_kept,
        "n_gold": snap.n_gold,
        "posterior_min": snap.posterior_min,
        "posterior_max": snap.posterior_max,
        "posterior_mean": snap.posterior_mean,
        "posterior_median": snap.posterior_median,
        "posterior_p95": snap.posterior_p95,
        "tier_counts": snap.tier_counts,
        "gold_sample_ids": snap.gold_sample_ids,
        "gold_sample_reasons": snap.gold_sample_reasons,
        "alert": snap.alert,
    }

    # Primary: Supabase
    if repo is not None:
        try:
            ok = repo.insert_drift_snapshot(row)
            if ok:
                return  # done, no local-fallback
        except Exception as e:
            log.warning("drift_db_insert_fail_using_local_fallback", error=str(e))

    # Fallback: Local-JSONL
    with _RUNS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
