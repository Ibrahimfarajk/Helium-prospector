"""Bundesanzeiger Jahresabschluss-Cross-Reference via Playwright.

httpx-Variante schlug fehl mit 302 → /error (JS-Session-Cookies erforderlich).
Playwright mit shared Persistent-Context löst das.

Strategie:
- 5-20 gezielte Lookups/Tag (NICHT massen-crawl)
- Wieder-verwendet den selben Browser-Context wie handelsregister.de
- Bei Captcha: gracefully return None (Lead trotzdem erstellt, nur ohne EK)
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from pathlib import Path

import structlog
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import Stealth
from selectolax.parser import HTMLParser

from ..models import CompanyEnrichment

log = structlog.get_logger()


BUNDESANZEIGER_BASE = "https://www.bundesanzeiger.de"
PROFILE_DIR = Path.home() / ".helium-pipeline" / "browser-profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

_STEALTH = Stealth()


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
# Browser-Context (shared mit handelsregister-Crawler)
# ───────────────────────────────────────────────────────────────────────────


_browser_ctx: BrowserContext | None = None
_pw_handle: object | None = None


async def _get_context() -> BrowserContext:
    """Lazy-init persistent context, shared zwischen Aufrufen."""
    global _browser_ctx, _pw_handle
    if _browser_ctx is not None:
        return _browser_ctx

    _pw_handle = await async_playwright().start()
    _browser_ctx = await _pw_handle.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        args=["--disable-blink-features=AutomationControlled"],
    )
    return _browser_ctx


async def close_shared_context() -> None:
    global _browser_ctx, _pw_handle
    if _browser_ctx:
        try:
            await _browser_ctx.close()
        except Exception:
            pass
        _browser_ctx = None
    if _pw_handle:
        try:
            await _pw_handle.stop()
        except Exception:
            pass
        _pw_handle = None


# ───────────────────────────────────────────────────────────────────────────
# Public API — drop-in replacement für httpx-Version
# ───────────────────────────────────────────────────────────────────────────


async def fetch_company_enrichment(
    *,
    hrb_nummer: str,
    company_name: str,
    client=None,  # Kept for API compat — wird ignoriert (httpx-AsyncClient nicht mehr nötig)
) -> CompanyEnrichment | None:
    """Hole Bundesanzeiger-Jahresabschluss-Daten via Playwright.

    Returns CompanyEnrichment immer (minimal mit hrb_nummer wenn nichts gefunden).
    """
    log.info("bundesanzeiger_lookup", hrb=hrb_nummer, name=company_name[:50])

    context = await _get_context()
    page: Page | None = None
    try:
        page = await context.new_page()
        await _STEALTH.apply_stealth_async(page)

        # 1. Such-URL direkt aufrufen
        search_url = (
            f"{BUNDESANZEIGER_BASE}/pub/de/suchergebnis"
            f"?7-1.-top%7Esearch%7EgenericSearchForm-search_param={urllib.parse.quote(company_name)}"
        )
        # Fallback: einfacherer GET
        simple_url = (
            f"{BUNDESANZEIGER_BASE}/pub/de/suchergebnis?"
            f"btnSuchen=Suchen&search_param={urllib.parse.quote(company_name)}"
        )

        try:
            await page.goto(simple_url, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
        except Exception as e:
            log.warning("ba_initial_load_failed", error=str(e))
            return _build_minimal(hrb_nummer, company_name)

        html = await page.evaluate("() => document.documentElement.outerHTML")
        title = await page.title()
        if "Fehler" in title or "error" in page.url:
            log.info("ba_no_results_for_name", name=company_name)
            return _build_minimal(hrb_nummer, company_name)
        if any(kw in html.lower() for kw in ("captcha", "sicherheitsabfrage")):
            log.warning("ba_captcha", hrb=hrb_nummer)
            return _build_minimal(hrb_nummer, company_name)

        # 2. JA-Treffer suchen
        tree = HTMLParser(html)
        ja_link_node = None
        for link in tree.css("a"):
            txt = link.text() or ""
            if "Jahresabschluss" in txt or "Bilanz" in txt:
                ja_link_node = link
                break

        if not ja_link_node:
            log.info("ba_no_ja_link", hrb=hrb_nummer)
            return _build_minimal(hrb_nummer, company_name)

        ja_href = ja_link_node.attributes.get("href") or ""
        ja_url = (
            ja_href
            if ja_href.startswith("http")
            else f"{BUNDESANZEIGER_BASE}{ja_href if ja_href.startswith('/') else '/' + ja_href}"
        )

        # 3. JA laden
        try:
            await page.goto(ja_url, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("ba_ja_load_failed", error=str(e))
            return _build_minimal(hrb_nummer, company_name)

        detail_html = await page.evaluate("() => document.documentElement.outerHTML")
        detail_text = HTMLParser(detail_html).text(separator="\n")

        equity = extract_equity_from_ja_text(detail_text)
        balance = extract_balance_sum_from_ja_text(detail_text)
        year = extract_ja_year(detail_text)

        nm_lower = company_name.lower()
        return CompanyEnrichment(
            hrb_nummer=hrb_nummer,
            last_ja_year=year,
            equity_eur=equity,
            balance_sum_eur=balance,
            has_holding_in_name="holding" in nm_lower,
            has_vermoegen_in_name=("vermögen" in nm_lower or "vermogen" in nm_lower),
            has_family_office_hint=(
                "family office" in nm_lower or "familyoffice" in nm_lower
            ),
            has_us_business_hint=(
                "usa" in nm_lower or " us " in nm_lower or "us " in nm_lower
            ),
        )

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


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
