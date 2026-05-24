"""BaFin-Vermittler-Cross-Reference (Phase 6.5 Filter 5).

Pragmatischer Ansatz: BaFin hat keinen CSV-Direkt-Download,
also pflegen wir eine kuratierte Liste in shared/bafin_vermittler.json.

Pre-Mortem-Mitigation gegen User-Sorge "alle 2000 BaFin-registrierte
als anti_persona = false-positive": wir nur 5-50 direkte
Helium-/Sachwert-Konkurrenten manuell. Rest wird nicht gefiltert.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

log = structlog.get_logger()

_BAFIN_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "shared" / "bafin_vermittler.json"
)
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        _cache = json.loads(_BAFIN_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("bafin_list_load_failed", error=str(e))
        _cache = {"entries": []}
    return _cache


def _normalize(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[.,;]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def is_bafin_vermittler_match(*, company_name: str) -> tuple[bool, str | None]:
    """Returns (is_match, category) wenn Firma in BaFin-Liste als anti_persona steht."""
    norm = _normalize(company_name)
    for entry in _load().get("entries", []):
        entry_norm = entry.get("name_normalized", "").lower().strip()
        if entry_norm and entry_norm in norm and entry.get("anti_persona"):
            return (True, entry.get("category"))
    return (False, None)
