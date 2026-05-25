"""Bundesanzeiger Jahresabschluss-Cross-Reference via deutschland-Library.

Phase 8.2-Hotfix (2026-05-25): Bundesanzeiger hat seine Such-API geändert
(search_param→fulltext, /pub/de/suchergebnis→/pub/de/start, Wicket-Framework).
Eigenes Playwright-Scraping wurde damit instabil. Migration auf die `deutschland`-
Library (bundesAPI/deutschland), die das Captcha-Solving + Wicket-Submit über
ein integriertes ML-Modell stabil löst.

Strategie:
- get_reports(company_name) → list of Reports (alle Veröffentlichungen)
- Filter auf Jahresabschluss/Konzernabschluss
- Nimm den NEUESTEN JA
- Apply bestehende Regex-Parser (EK, Bilanzsumme, Cashflow, Profit, §-EStG)

WICHTIG: Library macht sync HTTP-Calls. Wir wrappen in asyncio.to_thread() um
den Pipeline-Async-Flow nicht zu blockieren.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

import structlog

from ..models import CompanyEnrichment

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Parsing (unchanged from httpx-Version)
# ───────────────────────────────────────────────────────────────────────────


_EQUITY_LINE_PATTERNS = [
    re.compile(r"Eigenkapital[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro)", re.IGNORECASE),
    re.compile(r"gez(?:eichnetes)?\.?\s*Kapital[^\d-]*(-?[\d.,]+)", re.IGNORECASE),
]
_BALANCE_SUM_PATTERNS = [
    re.compile(r"Bilanzsumme[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro)?", re.IGNORECASE),
]
# Phase 6.5-F1: Cashflow + Liquidität + Profitabilität
_LIQUID_ASSETS_PATTERNS = [
    re.compile(
        r"(?:Kassenbestand,?\s*(?:Bundesbank|Postbank)?[^\n]{0,80}?Kreditinstitut|Liquide\s+Mittel|Guthaben\s+bei\s+Kreditinstituten|Kassenbestand\s+und\s+Bankguthaben)[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro|TEUR|Mio)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bZahlungsmittel(?:\s+und\s+Zahlungsmittel[äa]quivalente)?\b[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro|TEUR|Mio)?",
        re.IGNORECASE,
    ),
]
_OPERATING_CASHFLOW_PATTERNS = [
    re.compile(
        r"(?:Cashflow|Mittelzufluss|Mittelabfluss)\s+(?:aus\s+(?:der\s+)?(?:laufenden\s+|operativen\s+|gew[öo]hnlichen\s+)?Gesch[äa]ftst[äa]tigkeit|aus\s+der\s+gew[öo]hnlichen\s+T[äa]tigkeit)[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro|TEUR|Mio)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bOperativer\s+Cashflow\b[^\d-]*(-?[\d.,]+)",
        re.IGNORECASE,
    ),
]
_PROFIT_PATTERNS = [
    re.compile(
        r"(?:Jahres(?:[üu]bersch(?:uss|ü)|fehlbetrag)|Bilanzgewinn|Bilanzverlust)[^\d-]*(-?[\d.,]+)\s*(?:EUR|€|Euro|TEUR|Mio)?",
        re.IGNORECASE,
    ),
]
_PARAGRAPH_PATTERNS = {
    "§16 EStG": re.compile(r"§\s*16\s*(?:Abs\.?\s*\d+\s*)?EStG", re.IGNORECASE),
    "§34 EStG": re.compile(r"§\s*34\s*(?:Abs\.?\s*\d+\s*)?EStG", re.IGNORECASE),
    "§7g EStG": re.compile(r"§\s*7g\s*EStG", re.IGNORECASE),
    "§6b EStG": re.compile(r"§\s*6b\s*EStG", re.IGNORECASE),
    "§15a EStG": re.compile(r"§\s*15a\s*EStG", re.IGNORECASE),
    "Veräußerungsgewinn": re.compile(r"\bver[äa]u[ßs]erungsgewinn\b", re.IGNORECASE),
    "IAB §7g": re.compile(r"\binvestitionsabzugsbetrag\b", re.IGNORECASE),
    "Reinvest §6b": re.compile(r"\breinvestitionsr[üu]cklage\b", re.IGNORECASE),
}
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _parse_euro_value(raw: str) -> float | None:
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_equity_from_ja_text(text: str) -> float | None:
    for pattern in _EQUITY_LINE_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_euro_value(m.group(1))
            if val:
                return val
    return None


def extract_balance_sum_from_ja_text(text: str) -> float | None:
    for pattern in _BALANCE_SUM_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_euro_value(m.group(1))
            if val and val > 0:
                return val
    return None


def _detect_unit_multiplier(text: str, match_start: int) -> float:
    """Erkennt 'TEUR' / 'Mio' / 'Mrd' im 40-Zeichen-Umfeld → Multiplier."""
    window = text[max(0, match_start):match_start + 200].lower()
    if "mrd" in window:
        return 1_000_000_000.0
    if "mio" in window:
        return 1_000_000.0
    if "teur" in window or "in tausend" in window or "(t€)" in window:
        return 1_000.0
    return 1.0


def extract_liquid_assets_from_ja_text(text: str) -> float | None:
    """Phase 6.5-F1: Extrahiere liquide Mittel (Kasse + Bank)."""
    for pattern in _LIQUID_ASSETS_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_euro_value(m.group(1))
            if val is None:
                continue
            mult = _detect_unit_multiplier(text, m.start())
            return val * mult
    return None


def extract_operating_cashflow_from_ja_text(text: str) -> float | None:
    """Phase 6.5-F1: Extrahiere Cashflow aus laufender Geschäftstätigkeit."""
    for pattern in _OPERATING_CASHFLOW_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_euro_value(m.group(1))
            if val is None:
                continue
            mult = _detect_unit_multiplier(text, m.start())
            return val * mult
    return None


def extract_profit_from_ja_text(text: str) -> float | None:
    """Phase 6.5-F1: Extrahiere Jahresüberschuss/Bilanzgewinn."""
    for pattern in _PROFIT_PATTERNS:
        m = pattern.search(text)
        if m:
            val = _parse_euro_value(m.group(1))
            if val is None:
                continue
            # Bilanzverlust / Jahresfehlbetrag → negativ (matched-Wort selbst inspect)
            matched = m.group(0).lower()
            if "fehlbetrag" in matched or "bilanzverlust" in matched:
                val = -abs(val)
            mult = _detect_unit_multiplier(text, m.start())
            return val * mult
    return None


def extract_paragraph_matches(text: str) -> list[str]:
    """Phase 6.5-F3: Welche §-Trigger-Paragrafen erscheinen im JA-Text?"""
    return [label for label, pat in _PARAGRAPH_PATTERNS.items() if pat.search(text)]


def extract_ja_year(text: str) -> int | None:
    matches = _YEAR_PATTERN.findall(text)
    if not matches:
        return None
    from datetime import date
    current_year = date.today().year
    years = sorted({int(y) for y in matches}, reverse=True)
    for y in years:
        if 2010 <= y <= current_year:
            return y
    return None


# ───────────────────────────────────────────────────────────────────────────
# Public API — deutschland-Library statt eigenes Playwright-Scraping
# ───────────────────────────────────────────────────────────────────────────


def _select_latest_ja(reports: dict) -> tuple[str, dict] | tuple[None, None]:
    """Wähle den neuesten Jahresabschluss aus reports-dict.

    Library liefert {hash: {date, name, company, report, raw_report}}.
    Bevorzugt 'Jahresabschluss', fällt zurück auf 'Konzernabschluss'.
    """
    ja_candidates: list[tuple[datetime, str, dict]] = []
    konzern_candidates: list[tuple[datetime, str, dict]] = []
    for key, val in reports.items():
        name = (val.get("name") or "")
        date_val = val.get("date")
        if not isinstance(date_val, datetime):
            continue
        if "Jahresabschluss" in name:
            ja_candidates.append((date_val, key, val))
        elif "Konzernabschluss" in name:
            konzern_candidates.append((date_val, key, val))

    if ja_candidates:
        ja_candidates.sort(key=lambda x: x[0], reverse=True)
        _, key, val = ja_candidates[0]
        return key, val
    if konzern_candidates:
        konzern_candidates.sort(key=lambda x: x[0], reverse=True)
        _, key, val = konzern_candidates[0]
        return key, val
    return None, None


def _fetch_reports_sync(company_name: str) -> dict | None:
    """Sync-Aufruf der deutschland-Library. Wird via to_thread asynchron."""
    try:
        from deutschland.bundesanzeiger import Bundesanzeiger
        ba = Bundesanzeiger()
        return ba.get_reports(company_name)
    except Exception as e:
        log.warning("ba_library_call_failed", error=str(e), name=company_name[:50])
        return None


async def fetch_company_enrichment(
    *,
    hrb_nummer: str,
    company_name: str,
    client=None,  # Kept for API compat — wird ignoriert
) -> CompanyEnrichment | None:
    """Hole Bundesanzeiger-Jahresabschluss-Daten via deutschland-Library.

    Returns CompanyEnrichment immer (minimal mit hrb_nummer wenn nichts gefunden).
    """
    log.info("bundesanzeiger_lookup", hrb=hrb_nummer, name=company_name[:50])

    # Library macht sync HTTP — wrap in thread damit asyncio nicht blockt
    reports = await asyncio.to_thread(_fetch_reports_sync, company_name)

    if not reports:
        log.info("ba_no_reports", name=company_name[:50])
        return _build_minimal(hrb_nummer, company_name)

    key, ja = _select_latest_ja(reports)
    if not ja:
        log.info("ba_no_ja_found", name=company_name[:50], report_count=len(reports))
        return _build_minimal(hrb_nummer, company_name)

    text = ja.get("report") or ""
    if not text:
        log.warning("ba_ja_empty_report", name=company_name[:50])
        return _build_minimal(hrb_nummer, company_name)

    # Parser-Funktionen sind unverändert — Volltext aus Library statt aus HTML
    equity = extract_equity_from_ja_text(text)
    balance = extract_balance_sum_from_ja_text(text)
    # Date aus Library (datetime) bevorzugt vor Text-Extraktion
    ja_date = ja.get("date")
    year = ja_date.year if isinstance(ja_date, datetime) else extract_ja_year(text)
    liquid = extract_liquid_assets_from_ja_text(text)
    cashflow = extract_operating_cashflow_from_ja_text(text)
    profit = extract_profit_from_ja_text(text)
    para_hits = extract_paragraph_matches(text)

    log.info(
        "ba_enrichment_success",
        name=company_name[:50],
        year=year,
        equity=equity,
        balance=balance,
        liquid=liquid,
        cashflow=cashflow,
        profit=profit,
        paragraphs=len(para_hits),
    )

    nm_lower = company_name.lower()
    return CompanyEnrichment(
        hrb_nummer=hrb_nummer,
        last_ja_year=year,
        equity_eur=equity,
        balance_sum_eur=balance,
        liquid_assets_eur=liquid,
        operating_cashflow_eur=cashflow,
        profit_eur=profit,
        has_paragraph_match=bool(para_hits),
        paragraph_matches=para_hits,
        has_holding_in_name="holding" in nm_lower,
        has_vermoegen_in_name=("vermögen" in nm_lower or "vermogen" in nm_lower),
        has_family_office_hint=(
            "family office" in nm_lower or "familyoffice" in nm_lower
        ),
        has_us_business_hint=(
            "usa" in nm_lower or " us " in nm_lower or "us " in nm_lower
        ),
    )


async def close_shared_context() -> None:
    """Kept for API-compat — Library hat keinen Browser-Context mehr."""
    return None


def _build_minimal(hrb_nummer: str, company_name: str) -> CompanyEnrichment:
    """Minimal-Enrichment ohne EK — Soft-Signals aus Firmenname allein."""
    nm_lower = company_name.lower()
    return CompanyEnrichment(
        hrb_nummer=hrb_nummer,
        has_holding_in_name="holding" in nm_lower,
        has_vermoegen_in_name=("vermögen" in nm_lower or "vermogen" in nm_lower),
        has_family_office_hint=(
            "family office" in nm_lower or "familyoffice" in nm_lower
        ),
        has_us_business_hint=(
            "usa" in nm_lower or " us " in nm_lower or "us " in nm_lower
        ),
    )
