"""Bundesanzeiger Jahresabschluss-Cross-Reference.

Gezielter Lookup: für eine konkrete Firma (HRB + Name) prüfen ob ein Jahres-
abschluss veröffentlicht ist und falls ja, Eigenkapital extrahieren.

Anders als der HR-Crawler: kein Massen-Crawl, nur 5-20 gezielte Lookups/Tag.
Captcha-Risiko niedrig wenn rate-limited.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
import structlog
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import CompanyEnrichment

log = structlog.get_logger()


BUNDESANZEIGER_SEARCH_URL = "https://www.bundesanzeiger.de/pub/de/suchergebnis"


# ───────────────────────────────────────────────────────────────────────────
# Extraktion: EK aus Jahresabschluss-Text
# ───────────────────────────────────────────────────────────────────────────

# Vermögensindikatoren aus Bilanz
_EQUITY_LINE_PATTERNS = [
    re.compile(
        r"Eigenkapital[^\d-]*([\d.,]+)\s*(?:EUR|€|Euro)",
        re.IGNORECASE,
    ),
    re.compile(
        r"gez(?:eichnetes)?\.?\s*Kapital[^\d-]*([\d.,]+)",
        re.IGNORECASE,
    ),
]

_BALANCE_SUM_PATTERNS = [
    re.compile(
        r"Bilanzsumme[^\d-]*([\d.,]+)\s*(?:EUR|€|Euro)?",
        re.IGNORECASE,
    ),
]

_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")


def _parse_euro_value(raw: str) -> float | None:
    """'1.234.567,89' → 1234567.89"""
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
            if val and val > 0:
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


def extract_ja_year(text: str) -> int | None:
    matches = _YEAR_PATTERN.findall(text)
    if not matches:
        return None
    # neuester Jahres-Indikator
    years = sorted({int(y) for y in matches}, reverse=True)
    current_year = date.today().year
    for y in years:
        if 2010 <= y <= current_year:
            return y
    return None


# ───────────────────────────────────────────────────────────────────────────
# Public Lookup
# ───────────────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=30),
    reraise=True,
)
async def fetch_company_enrichment(
    *,
    hrb_nummer: str,
    company_name: str,
    client: httpx.AsyncClient,
) -> CompanyEnrichment | None:
    """Hole Bundesanzeiger JA-Daten für eine konkrete Firma.

    Strategie:
    1. Suche nach Firmenname auf bundesanzeiger.de
    2. Identifiziere ersten Jahresabschluss-Treffer
    3. Lade JA, extrahiere EK + Bilanzsumme + Jahr

    Returns None wenn nichts gefunden — kein Fehler.
    """
    log.info("bundesanzeiger_lookup", hrb=hrb_nummer, name=company_name)

    try:
        resp = await client.get(
            BUNDESANZEIGER_SEARCH_URL,
            params={
                "btnSuchen": "Suchen",
                "search_param": company_name,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("bundesanzeiger_http_fail", error=str(e))
        return None

    html = resp.text
    if any(
        kw in html.lower()
        for kw in ("captcha", "sicherheitsabfrage", "wir möchten sicher sein")
    ):
        log.warning("bundesanzeiger_captcha", hrb=hrb_nummer)
        return None

    # JA-Treffer in den Ergebnissen
    tree = HTMLParser(html)
    # Klassifikation "Jahresabschluss" oder "Konzernabschluss"
    ja_link = None
    for link in tree.css("a"):
        if "Jahresabschluss" in (link.text() or "") or "Bilanz" in (link.text() or ""):
            href = link.attributes.get("href")
            if href:
                ja_link = href
                break

    if not ja_link:
        log.info("kein_ja_in_bundesanzeiger", hrb=hrb_nummer)
        return CompanyEnrichment(hrb_nummer=hrb_nummer)

    # JA-Detail laden
    try:
        detail_url = ja_link if ja_link.startswith("http") else f"https://www.bundesanzeiger.de{ja_link}"
        detail_resp = await client.get(detail_url, timeout=20.0)
        detail_resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("bundesanzeiger_detail_fail", error=str(e))
        return CompanyEnrichment(hrb_nummer=hrb_nummer)

    detail_html = detail_resp.text
    detail_text = HTMLParser(detail_html).text(separator="\n")

    equity = extract_equity_from_ja_text(detail_text)
    balance = extract_balance_sum_from_ja_text(detail_text)
    year = extract_ja_year(detail_text)

    # Soft-Signals aus Firmenname
    nm_lower = company_name.lower()
    return CompanyEnrichment(
        hrb_nummer=hrb_nummer,
        last_ja_year=year,
        equity_eur=equity,
        balance_sum_eur=balance,
        has_holding_in_name="holding" in nm_lower,
        has_vermoegen_in_name=("vermögen" in nm_lower or "vermogen" in nm_lower),
        has_family_office_hint=("family office" in nm_lower or "familyoffice" in nm_lower),
        has_us_business_hint=("usa" in nm_lower or "us " in nm_lower or " us " in nm_lower),
    )
