"""Playwright-Crawler für handelsregister.de Bekanntmachungen.

Strategie:
- Daily-Run, fragt Bekanntmachungen der letzten 24h ab
- Stealth-Mode (realistischer Chrome-Fingerprint)
- Rate-Limit: 8-12 s Jitter zwischen Requests
- Retry-Logic: 3 Versuche, exponential backoff
- Persistente Browser-Profile (Cookies behalten)
- Bei Captcha: Pipeline pausiert + Notification

Wichtig: handelsregister.de hat ein JavaScript-getriebenes Such-Interface
mit Captcha-Schutz. Plain HTTP funktioniert nicht.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import structlog
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import Stealth
from selectolax.parser import HTMLParser

from ..models import BekanntmachungRaw, BekanntmachungType, CountryCode
from ..settings import settings

log = structlog.get_logger()


HR_SEARCH_URL = "https://www.handelsregister.de/rp_web/erweitertesuche.xhtml"
HR_BEKANNTMACHUNGEN_URL = "https://www.handelsregister.de/rp_web/bekanntmachungen.xhtml"

PROFILE_DIR = Path.home() / ".helium-pipeline" / "browser-profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)


# ───────────────────────────────────────────────────────────────────────────
# Klassifikator: Roh-Text → BekanntmachungType
# ───────────────────────────────────────────────────────────────────────────


_TYPE_PATTERNS: list[tuple[BekanntmachungType, re.Pattern[str]]] = [
    (
        BekanntmachungType.GF_CHANGE,
        re.compile(
            r"\b(geschäftsführer|bestellt|abberufen|nicht mehr geschäftsführer)\b",
            re.IGNORECASE,
        ),
    ),
    (
        BekanntmachungType.SHAREHOLDER_CHANGE,
        re.compile(
            r"\b(anteil|gesellschafter[- ]?wechsel|abtretung|übertragung)\b",
            re.IGNORECASE,
        ),
    ),
    (
        BekanntmachungType.NEW_REGISTRATION,
        re.compile(r"\b(neueintragung|neuangemeldet|gegründet)\b", re.IGNORECASE),
    ),
    (
        BekanntmachungType.CAPITAL_INCREASE,
        re.compile(r"\b(kapitalerhöhung|stammkapital erhöht)\b", re.IGNORECASE),
    ),
]


def classify_bekanntmachung(text: str) -> BekanntmachungType:
    for bt, pattern in _TYPE_PATTERNS:
        if pattern.search(text):
            return bt
    return BekanntmachungType.OTHER


# ───────────────────────────────────────────────────────────────────────────
# Sleep + Captcha-Detection
# ───────────────────────────────────────────────────────────────────────────


async def jittered_sleep() -> None:
    delay = random.uniform(
        settings.PIPELINE_RATE_LIMIT_MIN_SECONDS,
        settings.PIPELINE_RATE_LIMIT_MAX_SECONDS,
    )
    await asyncio.sleep(delay)


_CAPTCHA_INDICATORS = (
    "captcha",
    "Sicherheitsabfrage",
    "Bestätigen Sie, dass Sie kein Roboter sind",
    "h-captcha",
    "g-recaptcha",
)


def is_captcha_page(html: str) -> bool:
    lower = html.lower()
    return any(ind.lower() in lower for ind in _CAPTCHA_INDICATORS)


# ───────────────────────────────────────────────────────────────────────────
# Parser für Bekanntmachungs-Einträge
# ───────────────────────────────────────────────────────────────────────────


_HRB_PATTERN = re.compile(r"\bHRB\s*(\d+)\b")
_DATE_PATTERN = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def _extract_hrb(text: str) -> str | None:
    m = _HRB_PATTERN.search(text)
    return f"HRB {m.group(1)}" if m else None


def _extract_company_name(text: str) -> str:
    """Erste Zeile bis "GmbH"/"AG"/"UG"/"KG" — heuristisch."""
    for line in text.splitlines():
        line = line.strip()
        if any(
            suffix in line for suffix in ("GmbH", "AG", "UG", "KG", "OHG", "e.K.", "GbR")
        ):
            return line
    return text.splitlines()[0].strip()[:200] if text.strip() else "—"


def _extract_postal_code(text: str) -> str | None:
    m = re.search(r"\b(\d{5})\b", text)
    return m.group(1) if m else None


def _extract_city_after_postal(text: str) -> str | None:
    m = re.search(r"\b\d{5}\s+([A-ZÄÖÜ][\wäöüß.-]+(?:\s[A-ZÄÖÜ][\wäöüß.-]+)*)", text)
    return m.group(1).strip() if m else None


def parse_bekanntmachung_card(
    html_fragment: str,
    *,
    crawl_run_id: UUID,
    source: str = "handelsregister.de",
) -> BekanntmachungRaw | None:
    """Parse einen Bekanntmachungs-Card-HTML-Block aus der Ergebnis-Liste."""
    tree = HTMLParser(html_fragment)
    text = tree.text(separator="\n").strip()
    if not text:
        return None

    hrb = _extract_hrb(text)
    company = _extract_company_name(text)
    postal = _extract_postal_code(text)
    city = _extract_city_after_postal(text)
    bt = classify_bekanntmachung(text)

    # Datum: erstes Datum im Text
    m = _DATE_PATTERN.search(text)
    if not m:
        log.warning("kein_datum_im_eintrag", text=text[:200])
        return None
    bek_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    return BekanntmachungRaw(
        source=source,
        bekanntmachung_type=bt,
        hrb_nummer=hrb,
        company_name=company,
        company_postal_code=postal,
        company_city=city,
        country_code=CountryCode.DE,
        bekanntmachung_date=bek_date,
        raw_text=text,
        raw_html=html_fragment[:5000],  # cap to 5 KB pro Eintrag
        parsed_payload={},
        crawl_run_id=crawl_run_id,
    )


# ───────────────────────────────────────────────────────────────────────────
# Crawler: Browser-Context + Page-Iterator
# ───────────────────────────────────────────────────────────────────────────


async def _new_stealth_context() -> tuple[asyncio.Task, BrowserContext]:
    """Erstelle Persistent-Context mit Stealth-Plugin."""
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=settings.HEADLESS,
        user_agent=settings.PIPELINE_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
    )
    return pw, context


_STEALTH = Stealth()


async def _stealth_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    await _STEALTH.apply_stealth_async(page)
    return page


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


async def crawl_bekanntmachungen(
    *,
    crawl_run_id: UUID,
    days_back: int = 1,
    max_pages: int = 5,
) -> AsyncIterator[BekanntmachungRaw]:
    """
    Async-Generator: yieldet BekanntmachungRaw pro gefundenem Eintrag.

    days_back = 1 → letzte 24h
    max_pages = obere Sicherheits-Grenze (~50/Seite pro page)

    Bei Captcha-Erkennung: raised CaptchaDetected (Caller entscheidet).
    """
    pw, context = await _new_stealth_context()
    try:
        page = await _stealth_page(context)

        log.info("crawl_start", url=HR_BEKANNTMACHUNGEN_URL, days_back=days_back)
        await page.goto(HR_BEKANNTMACHUNGEN_URL, wait_until="domcontentloaded", timeout=30_000)
        # handelsregister.de fired multiple redirects + PrimeFaces-polls.
        # Wir warten geduldig auf das body-element + zusätzlich auf Stabilität.
        await page.wait_for_selector("body", timeout=15_000)
        await asyncio.sleep(2)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await jittered_sleep()

        html = await _safe_content(page)
        if is_captcha_page(html):
            log.error("captcha_detected", url=page.url)
            raise CaptchaDetected("handelsregister.de Captcha auf Landing-Page")

        # Datum-Filter: in das Formular eintragen
        today = date.today()
        from_date = today - timedelta(days=days_back)
        await _set_date_range(page, from_date, today)
        await jittered_sleep()

        # Such-Button klicken
        await _trigger_search(page)

        for page_num in range(max_pages):
            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            await asyncio.sleep(2)
            html = await _safe_content(page)
            if is_captcha_page(html):
                log.error("captcha_detected_on_page", page=page_num)
                raise CaptchaDetected(f"Captcha auf Ergebnis-Seite {page_num}")

            count = 0
            for card_html in _extract_result_cards(html):
                bek = parse_bekanntmachung_card(card_html, crawl_run_id=crawl_run_id)
                if bek:
                    count += 1
                    yield bek

            log.info("page_processed", page_num=page_num, items_found=count)

            # Nächste Seite — Bedingung: gibts "Weiter"-Button?
            has_next = await _click_next_page(page)
            if not has_next:
                log.info("no_more_pages", page_num=page_num)
                break

            await jittered_sleep()

    finally:
        await context.close()
        await pw.stop()


class CaptchaDetected(RuntimeError):
    """Pipeline pausiert, Notification an Admin."""


async def _safe_content(page: Page, retries: int = 3) -> str:
    """page.content() mit Retry — handelsregister.de polled mit PrimeFaces."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return await page.evaluate(
                "() => document.documentElement.outerHTML"
            )
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"page.content failed after {retries} retries: {last_err}")


# ───────────────────────────────────────────────────────────────────────────
# Page-Interaktion (kann sich ändern wenn handelsregister.de UI updated)
# ───────────────────────────────────────────────────────────────────────────


async def _set_date_range(page: Page, from_date: date, to_date: date) -> None:
    """Setze Datum-Filter im Bekanntmachungs-Formular.

    Selektoren basierend auf handelsregister.de Stand 2026-05.
    Bei UI-Änderung: hier anpassen.
    """
    try:
        # ID-Pattern aus handelsregister.de's PrimeFaces-UI
        from_input = page.locator("input[id*='vondatum']").first
        to_input = page.locator("input[id*='bisdatum']").first
        if await from_input.count() > 0:
            await from_input.fill(from_date.strftime("%d.%m.%Y"))
        if await to_input.count() > 0:
            await to_input.fill(to_date.strftime("%d.%m.%Y"))
    except Exception as e:
        log.warning("date_range_set_failed", error=str(e))


async def _trigger_search(page: Page) -> None:
    """Klicke Such-Button."""
    try:
        # häufiger Pattern bei PrimeFaces: button mit "Suche"-Label
        btn = page.locator("button:has-text('Suche')").first
        if await btn.count() > 0:
            await btn.click()
            return
        # Fallback: form submit
        await page.evaluate(
            "() => { const f = document.querySelector('form'); if (f) f.submit(); }"
        )
    except Exception as e:
        log.warning("search_trigger_failed", error=str(e))


def _extract_result_cards(html: str) -> list[str]:
    """Extrahiere die einzelnen Bekanntmachungs-Block-HTMLs."""
    tree = HTMLParser(html)
    # PrimeFaces-Datatable rows oder card-divs — beide Patterns abdecken
    candidates: list[str] = []
    for selector in ("tr.ui-datatable-row", "div.bekanntmachung", "div.search-result"):
        for node in tree.css(selector):
            candidates.append(node.html or "")
    return candidates


async def _click_next_page(page: Page) -> bool:
    """Klicke "Weiter"-Link. Return False wenn keiner mehr."""
    try:
        nxt = page.locator("a:has-text('Weiter'), a:has-text('Nächste')").first
        if await nxt.count() == 0:
            return False
        disabled = await nxt.get_attribute("aria-disabled")
        if disabled == "true":
            return False
        await nxt.click()
        return True
    except Exception as e:
        log.debug("next_page_click_failed", error=str(e))
        return False
