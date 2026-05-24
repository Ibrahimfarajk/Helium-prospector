"""Vorgänger-Fonds-Cross-Match (Phase 8.2 B3 — Real Implementation).

Cross-Referenz auf kuratierte Liste bekannter Schiffs-/Solar-/Container-/
Bio-Fonds + ihrer GFs/Vorstände/Initiatoren. Match auf Lead-Person-Last-
Name = starkes Sachwert-Mindset-Signal.

Datenquelle: `shared/predecessor_funds.json` (User-pflegbar, ~50 Einträge).

Match-Logik:
- Exact Last-Name + Schreibvarianten (Müller↔Mueller, Bindestriche, Initialen)
- First-Name optional (wenn da: muss matchen, sonst Last-Name allein reicht
  weil wir nur ~50 prominente Last-Names haben → False-Positive-Risiko low)

LR-Skala (Phase 8.2-Spec):
- 1 Hit:  ×3.0
- 2+ Hits: ×6.0

Family: affinitaet (User-Direktive: Sachwert-Mindset-Marker).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Pfade + Cache
# ───────────────────────────────────────────────────────────────────────────

_FUNDS_JSON = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "shared"
    / "predecessor_funds.json"
)

_funds_cache: list[dict] | None = None
# Pre-computed index: normalisierter Last-Name → list of (fund_name, person)
_name_index: dict[str, list[dict]] | None = None


PREDECESSOR_FUND_LRS = {
    "affinity_predecessor_fund_1": 3.0,
    "affinity_predecessor_fund_2plus": 6.0,
}


@dataclass(slots=True)
class PredecessorFundResult:
    """Result eines Cross-Matches."""

    matched_funds: list[str] = field(default_factory=list)
    matched_persons: list[str] = field(default_factory=list)
    lr_key: str | None = None
    lr_value: float | None = None


# ───────────────────────────────────────────────────────────────────────────
# Name-Normalisierung mit Schreibvarianten
# ───────────────────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    """Lowercase + ASCII-Variante + Bindestrich-zu-Space.

    Müller → mueller
    von der Heyde → von der heyde
    Schmidt-Künzel → schmidt kunzel
    """
    if not name:
        return ""
    s = name.lower().strip()
    # Umlaut-zu-ASCII
    repls = [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]
    for src, dst in repls:
        s = s.replace(src, dst)
    # Diakritika-Strip via Unicode-NFKD
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Bindestrich → Space
    s = s.replace("-", " ")
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _name_keys(name: str) -> set[str]:
    """Generiere mögliche Schreibvarianten für Index-Lookup."""
    if not name:
        return set()
    primary = _normalize_name(name)
    variants = {primary}
    # Bei mehrteiligen Namen auch einzelne Tokens
    for tok in primary.split():
        if len(tok) >= 3:
            variants.add(tok)
    return variants


# ───────────────────────────────────────────────────────────────────────────
# Load + Index
# ───────────────────────────────────────────────────────────────────────────


def _load_funds() -> list[dict]:
    global _funds_cache, _name_index
    if _funds_cache is not None:
        return _funds_cache
    try:
        data = json.loads(_FUNDS_JSON.read_text(encoding="utf-8"))
        _funds_cache = data.get("entries", [])
    except Exception as e:
        log.warning("predecessor_funds_load_failed", error=str(e))
        _funds_cache = []

    # Index aufbauen — pro normalisiertem Last-Name eine Liste der Treffer
    _name_index = {}
    for fund in _funds_cache:
        for person in fund.get("persons", []):
            last = person.get("last") or ""
            variants_extra = person.get("name_variants") or []
            keys: set[str] = set()
            keys |= _name_keys(last)
            for v in variants_extra:
                keys |= _name_keys(v)
            for k in keys:
                _name_index.setdefault(k, []).append({
                    "fund_name": fund.get("fund_name"),
                    "fund_type": fund.get("fund_type"),
                    "person": person,
                })
    return _funds_cache


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def lookup_predecessor_funds(
    *,
    person_first_name: str | None,
    person_last_name: str | None,
) -> PredecessorFundResult:
    """Cross-Match Lead-Person gegen Vorgänger-Fonds-Anbieter-Liste.

    Returns PredecessorFundResult mit gefundenen Fonds + LR-Key falls Hit.

    Match-Strategie:
    - Last-Name nach Normalisierung (Umlaut/Bindestrich/Diakritika)
    - Schreibvarianten aus JSON werden mit indexiert
    - Wenn first_name gegeben: muss zumindest Initial-Übereinstimmung haben
      (sonst False-Positive-Risiko bei häufigen Namen wie "Müller")
    """
    if not person_last_name:
        return PredecessorFundResult()

    _load_funds()
    if not _name_index:
        return PredecessorFundResult()

    keys = _name_keys(person_last_name)
    candidates: list[dict] = []
    for key in keys:
        candidates.extend(_name_index.get(key, []))

    if not candidates:
        return PredecessorFundResult()

    # Wenn first_name gegeben: Filtere auf Initial-Match (oder leerer first)
    if person_first_name:
        first_norm = _normalize_name(person_first_name)
        first_initial = first_norm[:1] if first_norm else ""
        filtered = []
        for c in candidates:
            cand_first = _normalize_name(c["person"].get("first") or "")
            cand_initial = cand_first[:1] if cand_first else ""
            # Match wenn keine first-info in JSON ODER Initial passt ODER full match
            if not cand_first:
                filtered.append(c)
            elif cand_initial == first_initial:
                filtered.append(c)
            elif cand_first == first_norm:
                filtered.append(c)
        candidates = filtered

    # Dedupe auf fund_name (eine Person kann in 2 Fonds sein)
    seen: set[str] = set()
    matched_funds: list[str] = []
    matched_persons: list[str] = []
    for c in candidates:
        fn = c["fund_name"]
        if fn in seen:
            continue
        seen.add(fn)
        matched_funds.append(fn)
        p = c["person"]
        matched_persons.append(f"{p.get('first', '')} {p.get('last', '')}".strip())

    if not matched_funds:
        return PredecessorFundResult()

    if len(matched_funds) >= 2:
        return PredecessorFundResult(
            matched_funds=matched_funds,
            matched_persons=matched_persons,
            lr_key="affinity_predecessor_fund_2plus",
            lr_value=PREDECESSOR_FUND_LRS["affinity_predecessor_fund_2plus"],
        )
    return PredecessorFundResult(
        matched_funds=matched_funds,
        matched_persons=matched_persons,
        lr_key="affinity_predecessor_fund_1",
        lr_value=PREDECESSOR_FUND_LRS["affinity_predecessor_fund_1"],
    )
