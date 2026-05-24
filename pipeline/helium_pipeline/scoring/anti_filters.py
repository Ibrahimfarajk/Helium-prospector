"""Anti-Filter (Phase 6.5).

Sechs Hard-/Soft-Filter die Junk- und ungeeignete Leads filtern:

1. Liquidations-Suffix (i.L., i.A., in Liquidation, in Abwicklung) — HARD
2. Briefkasten-Adresse (bekannte Anbieter + Cluster-Detection) — HARD/SOFT
3. Größenklasse §267 HGB (Sweet-Spot klein/mittel mit EK ≥500k) — HARD
4. Insolvenzbekanntmachung Cross-Ref — HARD
5. BaFin-Vermittler-Match — HARD
6. Online-Präsenz-Check — SOFT (LR-Penalty bei Stealth-Wealth-Schutz)

Reihenfolge: cheapest-first für maximale Pipeline-Effizienz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ───────────────────────────────────────────────────────────────────────────
# Filter 1: Liquidations-Suffix
# ───────────────────────────────────────────────────────────────────────────

# Pattern matched am Firmen-Namen-Ende oder als eigenes Wort
# "i.L." / "i. L." / "i.A." / "in Liquidation" / "in Abwicklung" / "i. Abw."
_LIQUIDATION_SUFFIX = re.compile(
    r"(?:"
    r"\bi\.?\s?L\.?\b"               # i.L. / i L
    r"|\bi\.?\s?A(?:bw)?\.?\b"       # i.A. / i.Abw.
    r"|\bin\s+(?:Liquidation|Abwicklung|Aufl[öo]sung)\b"
    r"|\b(?:Liquidations|Abwicklungs)gesellschaft\b"
    r"|\bGesellschaft\s+in\s+Liquidation\b"
    r"|—\s*gel[öo]scht\s*—"
    r")",
    re.IGNORECASE,
)


def is_liquidation_company(company_name: str) -> bool:
    """True wenn der Firmen-Name auf Liquidation/Abwicklung hindeutet."""
    return bool(_LIQUIDATION_SUFFIX.search(company_name))


# ───────────────────────────────────────────────────────────────────────────
# Filter 2: Briefkasten-Adresse (initial: bekannte Provider-Liste)
# ───────────────────────────────────────────────────────────────────────────

# Bekannte Coworking / Virtual-Office / Briefkasten-Provider in DACH.
# Erweiterbar — pflegbar in shared/briefkasten_addresses.json (Phase 6.5.2)
KNOWN_MAILBOX_PROVIDERS = {
    "regus",                   # größter virtual-office-Anbieter
    "wework",
    "spaces",                  # Regus-Tochter
    "officebusiness",
    "ecos office",
    "myhive",
    "satellite office",
    "design offices",
    "mindspace",
    "unicorn workspaces",
    "rent24",
    "techcode",
    "cloudbuilders",
    "agendis",
    "klagenfurt office",       # AT
    "biz center",
    "ucs office",
    "fourway",
}


def address_contains_mailbox_provider(address: str | None) -> str | None:
    """Returns provider-name wenn bekannter Briefkasten-Anbieter in Adresse, sonst None."""
    if not address:
        return None
    lower = address.lower()
    for provider in KNOWN_MAILBOX_PROVIDERS:
        if provider in lower:
            return provider
    return None


# ───────────────────────────────────────────────────────────────────────────
# Filter 3: Größenklasse §267 HGB
# ───────────────────────────────────────────────────────────────────────────


class SizeClass:
    SMALL = "small"        # ≤6M Bilanz, ≤12M Umsatz, ≤50 MA
    MEDIUM = "medium"      # ≤20M Bilanz, ≤40M Umsatz, ≤250 MA
    LARGE = "large"        # darüber
    UNKNOWN = "unknown"    # keine Daten


# Schwellwerte aus §267 HGB (Stand 2024+ — angepasst nach BilRUG)
SIZE_THRESHOLDS = {
    "small_balance_eur": 6_000_000,
    "small_revenue_eur": 12_000_000,
    "medium_balance_eur": 20_000_000,
    "medium_revenue_eur": 40_000_000,
}


def classify_size(
    *,
    balance_sum_eur: float | None,
    revenue_eur: float | None = None,
    employees: int | None = None,
) -> str:
    """§267 HGB Klassifikation. 2 von 3 Kriterien müssen erfüllt sein.

    Für unsere Pipeline meist nur balance_sum verfügbar — dann
    treffen wir grobe Einschätzung basierend allein auf Bilanzsumme.
    """
    if balance_sum_eur is None:
        return SizeClass.UNKNOWN

    if balance_sum_eur <= SIZE_THRESHOLDS["small_balance_eur"]:
        return SizeClass.SMALL
    if balance_sum_eur <= SIZE_THRESHOLDS["medium_balance_eur"]:
        return SizeClass.MEDIUM
    return SizeClass.LARGE


def is_sweet_spot_size(
    *,
    balance_sum_eur: float | None,
    equity_eur: float | None,
) -> bool:
    """Sweet-Spot für 38k-Ticket: klein/mittel mit EK ≥500k.

    - Klein zu wenig Liquidität: EK < 500k
    - Klein/Mittel mit EK ≥ 500k: GUT
    - Groß: Family-Office-Konkurrenz, schwer zu closen
    """
    if equity_eur is None or equity_eur < 500_000:
        return False
    size = classify_size(balance_sum_eur=balance_sum_eur)
    if size == SizeClass.LARGE:
        return False
    # Unknown → conservative TRUE (don't filter when we can't measure)
    return True


# ───────────────────────────────────────────────────────────────────────────
# Result-Dataclass
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class AntiFilterResult:
    """Aggregiertes Ergebnis aller Filter."""
    passed: bool
    rejected_by: list[str]
    soft_penalties: dict[str, float]  # LR-Penalties für Soft-Filter
    notes: dict[str, str]

    @classmethod
    def empty(cls) -> "AntiFilterResult":
        return cls(passed=True, rejected_by=[], soft_penalties={}, notes={})


def check_anti_filters(
    *,
    company_name: str,
    company_address: str | None = None,
    balance_sum_eur: float | None = None,
    equity_eur: float | None = None,
    has_online_presence: bool | None = None,
    is_insolvency: bool = False,
    is_bafin_vermittler: bool = False,
) -> AntiFilterResult:
    """Apply all 6 anti-filters in cost-optimal order. Returns aggregated result."""
    result = AntiFilterResult.empty()

    # Filter 1: Liquidation-Suffix (cheapest)
    if is_liquidation_company(company_name):
        result.passed = False
        result.rejected_by.append("liquidation_suffix")

    # Filter 2: Mailbox-Provider in Address
    if company_address:
        provider = address_contains_mailbox_provider(company_address)
        if provider:
            result.passed = False
            result.rejected_by.append(f"mailbox_provider:{provider}")

    # Filter 3: Size-Class (sweet-spot)
    if balance_sum_eur is not None or equity_eur is not None:
        if not is_sweet_spot_size(
            balance_sum_eur=balance_sum_eur, equity_eur=equity_eur
        ):
            size = classify_size(balance_sum_eur=balance_sum_eur)
            if size == SizeClass.LARGE:
                result.passed = False
                result.rejected_by.append("size_class:large")
            elif equity_eur is not None and equity_eur < 500_000:
                result.passed = False
                result.rejected_by.append("size_class:equity_too_low")
            result.notes["size_class"] = size

    # Filter 4: Insolvency cross-ref (extern, in main.py vorab gemacht)
    if is_insolvency:
        result.passed = False
        result.rejected_by.append("insolvency_record")

    # Filter 5: BaFin-Vermittler (extern, in main.py vorab gemacht)
    if is_bafin_vermittler:
        result.passed = False
        result.rejected_by.append("bafin_vermittler")

    # Filter 6 (SOFT): Online-Präsenz
    # Wenn has_online_presence == False (explicit nicht gefunden), LR-Penalty.
    # Wenn None (nicht geprüft), kein Penalty.
    if has_online_presence is False:
        result.soft_penalties["no_online_presence"] = 0.5
        result.notes["online_presence"] = "not_found"

    return result
