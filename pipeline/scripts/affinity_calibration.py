"""Pattern-Calibration: testet AFFINITY_CATEGORIES gegen den 4.4-MB Live-Dump.

Ziel: jede Kategorie sollte 0.05-2% der Bekanntmachungen treffen.
- helium_direct: 0.05-0.3% erwartet (sehr selten)
- sachwerte_konkret: 0.1-0.5% erwartet
- us_link: 0.5-2% erwartet
- tax_struct_premium: 0.3-1% erwartet

Bei >5% pro Kategorie → Pattern zu locker → fix.
Bei 0% pro Kategorie → Pattern zu eng → fix.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from helium_pipeline.crawlers.handelsregister import parse_results_page

DUMP_FILE = Path(__file__).parent.parent / "local_data" / "hr_dumps" / "03_bekanntmachungen.html"


# Test-Patterns (Vorschlag vor Refactor in scoring/bayes.py)
AFFINITY_CATEGORIES = {
    "helium_direct": {
        "lr": 30.0,
        "patterns": [
            re.compile(r"\bhelium\b", re.IGNORECASE),
            re.compile(r"\bedelgas[es]?\b", re.IGNORECASE),
            re.compile(r"\bindustriegas\b", re.IGNORECASE),
            re.compile(r"\bkryo(?:technik|gen)\b", re.IGNORECASE),
            re.compile(r"\bgaschromatograph", re.IGNORECASE),
            re.compile(r"\b(?:MRT|magnetresonanz|kernspintomograph)\b", re.IGNORECASE),
            re.compile(r"\bhalbleiterprodukti", re.IGNORECASE),  # nicht generisch "halbleiter"
            re.compile(r"\braketenantrieb\b", re.IGNORECASE),
            re.compile(r"\bschutzgas\b", re.IGNORECASE),
        ],
    },
    "sachwerte_konkret": {
        "lr": 12.0,
        "patterns": [
            re.compile(r"\borri\b", re.IGNORECASE),
            re.compile(r"\broyalt(?:y|ies)\b", re.IGNORECASE),
            re.compile(r"\b(?:öl|oil|gas|mineral|edelmetall|gold|silber)[- ]?förder", re.IGNORECASE),
            re.compile(r"\bsachwert[a-z]*\b", re.IGNORECASE),
            re.compile(r"\bdirektinvest", re.IGNORECASE),
            re.compile(r"\bphysisch[- ]?hinterleg", re.IGNORECASE),
            re.compile(r"\brohstoff(?:invest|fonds)", re.IGNORECASE),
            re.compile(r"\bförderrecht\b", re.IGNORECASE),
        ],
    },
    "us_link": {
        "lr": 6.0,
        "patterns": [
            re.compile(r"\b(?:Texas|Oklahoma|Kansas|Wyoming|Utah|Arizona|Nevada|Colorado|Montana)\b"),
            re.compile(r"\bUS[- ]?(?:Tochter|Kooperation|Partner|Operations)\b"),
            re.compile(r"\bUSA?[- ]?(?:Geschäft|Markt|Vertrieb)\b"),
        ],
    },
    "tax_struct_premium": {
        "lr": 5.0,
        "patterns": [
            re.compile(r"\bstiftung(?:en)?\b", re.IGNORECASE),
            re.compile(r"\bfamily[- ]?office\b", re.IGNORECASE),
            re.compile(r"\btreuhand\b", re.IGNORECASE),
            re.compile(r"\bsingle[- ]?family[- ]?office\b", re.IGNORECASE),
        ],
    },
}


def category_match(cat_name: str, text: str) -> bool:
    """True wenn mindestens 1 Pattern der Kategorie matched."""
    cat = AFFINITY_CATEGORIES[cat_name]
    return any(p.search(text) for p in cat["patterns"])


def main() -> int:
    if not DUMP_FILE.exists():
        print(f"ERROR: dump file fehlt: {DUMP_FILE}")
        return 1

    print(f"Loading {DUMP_FILE.stat().st_size:,} bytes...")
    html = DUMP_FILE.read_text(encoding="utf-8")
    items = parse_results_page(html, crawl_run_id=uuid4())
    print(f"Parsed: {len(items)} Bekanntmachungen\n")

    print("=" * 75)
    print(f"{'Category':25} {'Matches':>10} {'%':>8}  Pattern-Detail")
    print("=" * 75)

    category_hits: dict[str, list] = {k: [] for k in AFFINITY_CATEGORIES}

    for item in items:
        full_text = item.company_name + " " + (item.raw_text or "")
        for cat in AFFINITY_CATEGORIES:
            if category_match(cat, full_text):
                category_hits[cat].append(item)

    for cat in AFFINITY_CATEGORIES:
        hits = category_hits[cat]
        pct = 100.0 * len(hits) / len(items) if items else 0
        marker = "✓" if 0.01 <= pct <= 5 else ("⚠ZU_LOCKER" if pct > 5 else "⚠ZU_ENG")
        print(f"{cat:25} {len(hits):>10}  {pct:>6.2f}%  {marker}")

    print()
    print("=" * 75)
    print("MULTI-CATEGORY-HITS (≥2 Kategorien = T1-GOLD-Kandidat):")
    print("=" * 75)
    multi_hits = []
    for item in items:
        full_text = item.company_name + " " + (item.raw_text or "")
        cats = [cat for cat in AFFINITY_CATEGORIES if category_match(cat, full_text)]
        if len(cats) >= 2:
            multi_hits.append((item, cats))

    print(f"\n  ≥2 Kategorien: {len(multi_hits)} / {len(items)} ({100*len(multi_hits)/len(items):.3f}%)")
    print(f"  davon mit helium_direct: {sum(1 for _, c in multi_hits if 'helium_direct' in c)}")

    if multi_hits:
        print("\n  Top-15 Multi-Hits:")
        for item, cats in multi_hits[:15]:
            print(f"    {item.bekanntmachung_date}  {item.register_court:18}  "
                  f"{item.company_name[:55]}\n      Kategorien: {cats}")

    print()
    print("=" * 75)
    print("HELIUM-DIRECT HITS (alle):")
    print("=" * 75)
    for item in category_hits["helium_direct"][:10]:
        print(f"  {item.bekanntmachung_date} {item.register_court:15} {item.company_name}")
    if len(category_hits["helium_direct"]) > 10:
        print(f"  ... +{len(category_hits['helium_direct']) - 10} weitere")

    print()
    print("=" * 75)
    print("SACHWERTE-KONKRET HITS (Sample 10):")
    print("=" * 75)
    for item in category_hits["sachwerte_konkret"][:10]:
        print(f"  {item.bekanntmachung_date} {item.register_court:15} {item.company_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
