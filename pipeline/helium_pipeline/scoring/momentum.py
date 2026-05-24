"""Momentum-Score (Phase 8.2 B1).

Misst Burst-Aktivität: ≥2 Trigger-Events innerhalb 90 Tagen für dieselbe
Firma → starkes Signal aktiver Vermögensbewegung.

Datenquelle: bekanntmachungen_raw-Tabelle in Supabase.
Identifikator: hrb_nummer (eindeutig pro Firma). Wenn fehlt: company_name
normalisiert.

Multiplikator-Skala:
  1 Trigger:  ×1.0  (keine Momentum-Verstärkung)
  2 Trigger:  ×2.0
  3 Trigger:  ×3.0
  4+ Trigger: ×3.5
  Cap bei ×5 (auch bei 10+ Triggers).

Family: aktivitaet (User-Direktive).

LR-Key: `momentum_score_N` wobei N die Anzahl ist.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Momentum-LR-Skala
# ───────────────────────────────────────────────────────────────────────────

MOMENTUM_WINDOW_DAYS = 90
MOMENTUM_CAP = 5.0
MOMENTUM_LR_BY_COUNT = {
    2: 2.0,
    3: 3.0,
    4: 3.5,
    5: 4.0,
    6: 4.5,
}


def _momentum_lr(count: int) -> float:
    if count <= 1:
        return 1.0
    return min(MOMENTUM_LR_BY_COUNT.get(count, MOMENTUM_CAP), MOMENTUM_CAP)


def _normalize_company(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def compute_momentum_lr(
    *,
    hrb_nummer: str | None,
    company_name: str,
    today: date,
    other_bekanntmachungen: list[dict],
) -> tuple[float | None, int, str]:
    """Berechne Momentum-LR.

    Args:
        hrb_nummer: bevorzugte ID (eindeutig).
        company_name: Fallback wenn HRB fehlt.
        today: für Window-Bestimmung.
        other_bekanntmachungen: list of {hrb_nummer, company_name, bekanntmachung_date}
            (alle vorherigen Bekanntmachungen der DB, inkl. aktueller).

    Returns:
        (lr_value or None, count, reason)
        lr_value=None wenn keine Momentum-Aktivität.
    """
    window_start = today - timedelta(days=MOMENTUM_WINDOW_DAYS)
    target_norm = _normalize_company(company_name)

    count = 0
    for other in other_bekanntmachungen:
        # Date-Window
        other_date = other.get("bekanntmachung_date")
        if isinstance(other_date, str):
            try:
                other_date = date.fromisoformat(other_date)
            except ValueError:
                continue
        if not isinstance(other_date, date):
            continue
        if other_date < window_start or other_date > today:
            continue

        # Match auf HRB (bevorzugt) oder Namen
        other_hrb = other.get("hrb_nummer")
        if hrb_nummer and other_hrb and other_hrb == hrb_nummer:
            count += 1
            continue
        # Fallback: Namens-Match wenn keine HRB-IDs verfügbar
        if not (hrb_nummer and other_hrb):
            other_name = other.get("company_name", "")
            if _normalize_company(other_name) == target_norm:
                count += 1

    if count <= 1:
        return (None, count, "single_trigger")

    lr = _momentum_lr(count)
    return (lr, count, f"{count}_triggers_in_{MOMENTUM_WINDOW_DAYS}d")
