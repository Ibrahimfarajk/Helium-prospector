"""Affinity-Signal-Detection (Phase 6.1).

Drei Quellen für Helium-/Sachwert-/US-/Tax-Affinität:

A) PATTERN-MATCH auf Firmen-Name (sofort verfügbar)
   - helium_direct: explizite Helium/Edelgas-Begriffe (sehr selten, ~0%)
   - sachwerte_konkret: Edelmetall/Rohstoff/Sachwert-Begriffe (~0.12%)
   - us_link: US-Bundesstaaten / LLC / US-Tochter (~0.23%)
   - tax_struct_premium: Stiftung/Family Office/Treuhand (~0.26%)

B) BUNDESANZEIGER-JA-TEXT-SCAN
   Wenn Bundesanzeiger-Enrichment den JA lädt, scannen wir den Volltext
   nach den gleichen Patterns. Treffer dort sind hochwertiger (echter
   Geschäftstätigkeitsbericht). Speicher als CompanyEnrichment-Flag.

C) WATCH-LIST (shared/helium_watch.json)
   Manuell gepflegte Liste von Firmen mit bekanntem Helium-Bezug.
   Exact-Match auf name_normalized ODER hrb_nummer → höchster Boost.
   Auch Anti-Persona-Filter (Konkurrenz/Issuer ausschließen).

T1-GOLD-Label hat 3 Pfade:
   1) Helium-Direct-Hit → IMMER GOLD
   2) Posterior ≥ 0.30 → GOLD (sehr hoher Score)
   3) Posterior ≥ 0.15 + ≥2 Affinity-Categories getroffen → GOLD
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Pattern-Definitions
# ───────────────────────────────────────────────────────────────────────────

# Kalibriert gegen 4.4-MB Live-Dump (siehe scripts/affinity_calibration.py)
# Match-Rate-Erwartung pro Kategorie: 0.05-0.5% auf Firmen-Namen, 1-3% auf JA-Volltext.

AFFINITY_CATEGORIES: dict[str, dict] = {
    "helium_direct": {
        "lr": 30.0,
        "label": "Helium/Edelgas-Industrie",
        "patterns": [
            re.compile(r"\bhelium\b", re.IGNORECASE),
            re.compile(r"\bedelgas[es]?\b", re.IGNORECASE),
            re.compile(r"\bindustriegas[ea]?\b", re.IGNORECASE),
            re.compile(r"\bkryo(?:technik|gen)\b", re.IGNORECASE),
            re.compile(r"\bgaschromatograph", re.IGNORECASE),
            re.compile(r"\b(?:MRT|magnetresonanz|kernspintomograph)\b", re.IGNORECASE),
            re.compile(r"\bhalbleiterprodukti", re.IGNORECASE),
            re.compile(r"\braketenantrieb\b", re.IGNORECASE),
            re.compile(r"\bschutzgas\b", re.IGNORECASE),
            re.compile(r"\bflüssighelium\b|\bfluessighelium\b", re.IGNORECASE),
        ],
    },
    "sachwerte_konkret": {
        "lr": 12.0,
        "label": "Sachwert-Affinität",
        "patterns": [
            re.compile(r"\borri\b", re.IGNORECASE),
            re.compile(r"\broyalt(?:y|ies)\b", re.IGNORECASE),
            re.compile(r"\b(?:öl|oil|gas|mineral|edelmetall|gold|silber)[- ]?förder", re.IGNORECASE),
            re.compile(r"\bsachwert[a-z]*\b", re.IGNORECASE),
            re.compile(r"\bdirektinvest", re.IGNORECASE),
            re.compile(r"\bphysisch[- ]?hinterleg", re.IGNORECASE),
            re.compile(r"\brohstoff[a-z]*\b", re.IGNORECASE),
            re.compile(r"\bedelmetall[a-z]*\b", re.IGNORECASE),
            re.compile(r"\b(?:gold|silber)[- ]?invest", re.IGNORECASE),
            re.compile(r"\bförderrecht\b", re.IGNORECASE),
            # "Beteiligung" BEWUSST RAUS — zu breit (würde 30% der GmbHs catchen)
        ],
    },
    "us_link": {
        "lr": 6.0,
        "label": "US-Verbindung",
        "patterns": [
            re.compile(r"\b(?:Texas|Oklahoma|Kansas|Wyoming|Utah|Arizona|Nevada|Colorado|Montana)\b"),
            re.compile(r"\b(?:LLC|Inc\.?)\b"),
            re.compile(r"\bUS[- ]?(?:Tochter|Kooperation|Partner|Operations|Geschäft)\b"),
            re.compile(r"\bUSA?[- ]?(?:Markt|Vertrieb|Operations|Aktivität)\b"),
            re.compile(r"\b(?:Delaware|Nevada)[- ]?(?:Corp|Corporation)\b"),
        ],
    },
    "tax_struct_premium": {
        "lr": 5.0,
        "label": "Steuer-/Vermögens-Struktur",
        "patterns": [
            re.compile(r"\bstiftung(?:en)?\b", re.IGNORECASE),
            re.compile(r"\bfamily[- ]?office\b", re.IGNORECASE),
            re.compile(r"\btreuhand\b", re.IGNORECASE),
            re.compile(r"\bsingle[- ]?family[- ]?office\b", re.IGNORECASE),
            # "Vermögensverwaltung" BEWUSST RAUS — schon als weiche LR (name_contains_vermoegen)
        ],
    },
}
# F3 §-Trigger-Match siehe bayes._collect_evidence — wird via
# CompanyEnrichment.has_paragraph_match aus dem Crawler eingehängt
# (Single-Source-of-Truth, kein Doppelcount mit affinity).

# Bonus-LR für Bundesanzeiger-JA-Volltext-Treffer (echter Geschäftstätigkeitsbericht)
JA_TEXT_BONUS_LR = 1.5  # multipliziert den Category-LR (z.B. helium 30 → 45 bei JA-Hit)

# Watch-List
WATCH_LIST_LR = 50.0  # höchster Boost — manuell kuratiert


# ───────────────────────────────────────────────────────────────────────────
# Watch-List
# ───────────────────────────────────────────────────────────────────────────

_WATCH_LIST_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "shared" / "helium_watch.json"
)
_watch_cache: dict | None = None


def _load_watch_list() -> dict:
    """Lade Watch-Liste lazy + cache."""
    global _watch_cache
    if _watch_cache is not None:
        return _watch_cache
    try:
        _watch_cache = json.loads(_WATCH_LIST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("watch_list_load_failed", error=str(e), path=str(_WATCH_LIST_PATH))
        _watch_cache = {"entries": []}
    return _watch_cache


def _normalize_name(name: str) -> str:
    """Normalisierung für robusten Match: lowercase, Whitespace-collapse, Punkte raus."""
    s = name.lower().strip()
    s = re.sub(r"[.,;]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def check_watch_list(
    *, company_name: str, hrb_nummer: str | None
) -> tuple[bool, str | None, bool]:
    """
    Returns: (is_match, category, is_anti_persona)
    """
    wl = _load_watch_list()
    norm = _normalize_name(company_name)
    for entry in wl.get("entries", []):
        entry_norm = entry.get("name_normalized", "").lower().strip()
        entry_hrb = entry.get("hrb_nummer")
        # Match auf normalisierte Substring ODER exact HRB
        name_match = bool(entry_norm) and entry_norm in norm
        hrb_match = bool(entry_hrb) and bool(hrb_nummer) and entry_hrb == hrb_nummer
        if name_match or hrb_match:
            return (True, entry.get("category"), bool(entry.get("anti_persona", False)))
    return (False, None, False)


# ───────────────────────────────────────────────────────────────────────────
# Pattern-Match
# ───────────────────────────────────────────────────────────────────────────


def _categories_matched(text: str) -> set[str]:
    """Welche Affinity-Kategorien matchen in `text`?"""
    hits: set[str] = set()
    for cat_name, cat in AFFINITY_CATEGORIES.items():
        for pattern in cat["patterns"]:
            if pattern.search(text):
                hits.add(cat_name)
                break
    return hits


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


def check_affinity_signals(
    *,
    company_name: str,
    raw_text: str | None = None,
    ja_text: str | None = None,
    hrb_nummer: str | None = None,
) -> dict[str, float]:
    """Sammle alle Affinity-LRs für einen Lead.

    Returns dict mit affinity_*-keys → LR-Werte.
    """
    lrs: dict[str, float] = {}

    # 1. Watch-List exact match (höchster Boost)
    watch_match, watch_category, is_anti = check_watch_list(
        company_name=company_name, hrb_nummer=hrb_nummer
    )
    if watch_match and not is_anti:
        lrs[f"affinity_watchlist_{watch_category or 'manual'}"] = WATCH_LIST_LR

    # 2. Pattern auf company_name + raw_text (sofort verfügbar)
    primary_text = company_name + " " + (raw_text or "")
    name_hits = _categories_matched(primary_text)
    for cat in name_hits:
        lrs[f"affinity_{cat}"] = AFFINITY_CATEGORIES[cat]["lr"]

    # 3. Pattern auf JA-Volltext (höherer Bonus)
    if ja_text:
        ja_hits = _categories_matched(ja_text)
        for cat in ja_hits:
            base_lr = AFFINITY_CATEGORIES[cat]["lr"]
            key = f"affinity_{cat}_ja_verified"
            # JA-Treffer erhöhen den LR-Bonus
            lrs[key] = base_lr * JA_TEXT_BONUS_LR
            # entferne den weniger sicheren name-only-Hit falls da
            lrs.pop(f"affinity_{cat}", None)

    return lrs


def is_anti_persona_watch_match(
    *, company_name: str, hrb_nummer: str | None
) -> bool:
    """True wenn Firma in Watch-List als anti_persona markiert ist (Konkurrenz/Issuer)."""
    _, _, is_anti = check_watch_list(
        company_name=company_name, hrb_nummer=hrb_nummer
    )
    return is_anti


# ───────────────────────────────────────────────────────────────────────────
# T1-GOLD-Logik
# ───────────────────────────────────────────────────────────────────────────

T1_GOLD_POSTERIOR_THRESHOLD = 0.30


def is_t1_gold(posterior: float, lrs: dict[str, float]) -> tuple[bool, str | None]:
    """
    Returns (is_gold, reason).

    Drei Pfade zu GOLD:
    1) Helium-Direct-Match oder Watch-List-Treffer (egal welcher Posterior)
       → AUSSER bei posterior < T1_THRESHOLD (würde dem Closer schaden)
    2) Posterior >= 0.30 → klares high-confidence
    3) Posterior >= 0.15 + ≥2 affinity_-Kategorien getroffen
    """
    from .bayes import T1_THRESHOLD  # avoid circular import at top

    has_helium_direct = "affinity_helium_direct" in lrs or "affinity_helium_direct_ja_verified" in lrs
    has_watchlist = any(k.startswith("affinity_watchlist_") for k in lrs)

    if posterior < T1_THRESHOLD:
        return (False, None)  # never GOLD without T1-level posterior

    if has_helium_direct:
        return (True, "helium_direct_match")
    if has_watchlist:
        return (True, "watchlist_match")
    if posterior >= T1_GOLD_POSTERIOR_THRESHOLD:
        return (True, "high_posterior")

    # Pfad 3: ≥2 distinct affinity categories
    # §-Match aus Bayes-Bridge (tax_paragraph_match_ja) zählt mit als Kategorie.
    distinct_cats = {
        k.replace("affinity_", "").replace("_ja_verified", "")
        for k in lrs
        if k.startswith("affinity_") and not k.startswith("affinity_watchlist_")
    }
    if "tax_paragraph_match_ja" in lrs:
        distinct_cats.add("tax_paragraph_match")
    if len(distinct_cats) >= 2:
        return (True, f"multi_category_{len(distinct_cats)}")

    return (False, None)
