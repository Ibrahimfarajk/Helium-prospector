"""Live-Crawler für handelsregister.de Bekanntmachungen.

Architektur (nach UI-Discovery 2026-05-25):
  1. GET /rp_web/welcome.xhtml → Sitzungshinweis-Modal
  2. Click `a.cookie-btn` ("Verstanden") → Cookie gesetzt
  3. Click `#naviForm:bekanntmachungenLink` → PrimeFaces-AJAX submit
  4. Bekanntmachungs-Seite mit Default-Liste der letzten 4 Wochen
  5. Parse `dl#bekanntMachungenForm:datalistId_list` → 52+ Einträge
  6. (optional) Set Datum-Filter + click `#bekanntMachungenForm:rrbSuche` → Refresh

Format jedes Result-Items:
  <dt>Datum (dd.MM.yyyy)</dt>
  <dd>
    <a onclick="fireBekanntmachungN(...)"><label>
      Bekanntmachungs-Typ<br>
      Bundesland Amtsgericht Ort HRB-Nummer<br>
      Firma — Ort
    </label></a>
    ... weitere Items pro Tag ...
  </dd>
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import AsyncIterator
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import structlog
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import Stealth
from selectolax.parser import HTMLParser

from ..models import BekanntmachungRaw, BekanntmachungType, CountryCode
from ..settings import settings

log = structlog.get_logger()


HR_WELCOME_URL = "https://www.handelsregister.de/rp_web/welcome.xhtml"

PROFILE_DIR = Path.home() / ".helium-pipeline" / "browser-profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

_STEALTH = Stealth()


# ───────────────────────────────────────────────────────────────────────────
# Classification: Bekanntmachungs-Text → Enum
# ───────────────────────────────────────────────────────────────────────────


_TYPE_PATTERNS: list[tuple[BekanntmachungType, re.Pattern[str]]] = [
    # Kalibriert auf REALE handelsregister.de Bekanntmachungs-Typen (Mai 2026)
    # Reihenfolge: spezifischer zuerst.

    # "Registerbekanntmachung nach dem Umwandlungsgesetz" → Verschmelzung/Spaltung
    # → starker Liquiditäts-Trigger, behandeln wie SHAREHOLDER_CHANGE
    (
        BekanntmachungType.SHAREHOLDER_CHANGE,
        re.compile(r"\b(umwandlungsgesetz|verschmelzung|spaltung|formwechsel)\b", re.IGNORECASE),
    ),
    # Klassische direkte Begriffe
    (
        BekanntmachungType.SHAREHOLDER_CHANGE,
        re.compile(
            r"\b(anteils?\s?(eigner|übertragung|abtretung)|gesellschafter[- ]?(wechsel|liste)|"
            r"übertragung\s+der\s+gesch[äa]ftsanteile|ver[äa]nderung\s+gesellschafter)\b",
            re.IGNORECASE,
        ),
    ),
    # "Einreichung neuer Dokumente" — häufigster Default-Eintrag, oft Gesellschafterliste-Update
    # Heuristik: tag this als SHAREHOLDER_CHANGE (würde mit Detail-Lookup verifiziert)
    (
        BekanntmachungType.SHAREHOLDER_CHANGE,
        re.compile(r"\beinreichung\s+neuer\s+dokumente\b", re.IGNORECASE),
    ),
    (
        BekanntmachungType.GF_CHANGE,
        re.compile(
            r"\b(gesch[äa]ftsf[üu]hrer|bestell(t|ung)|abberuf(en|ung)|vertretungs(berechtigt|befugnis))\b",
            re.IGNORECASE,
        ),
    ),
    (
        BekanntmachungType.NEW_REGISTRATION,
        re.compile(
            r"\b(neueintragung|neuangemeldet|gegr[üu]ndet|firma.{0,20}eingetragen|"
            r"erstanmeldung|neuanmeldung)\b",
            re.IGNORECASE,
        ),
    ),
    (
        BekanntmachungType.CAPITAL_INCREASE,
        re.compile(
            r"\b(kapitalerh[öo]hung|stammkapital\s+erh[öo]ht|kapitalherabsetzung)\b",
            re.IGNORECASE,
        ),
    ),
]


# Anti-Patterns: Lead-Killer Bekanntmachungen
_ANTI_PATTERN = re.compile(
    r"\b(löschungsank[üu]ndigung|gel[öo]scht|insolvenz|liquidation|abwicklung|aufl[öo]sung)\b",
    re.IGNORECASE,
)


def is_anti_pattern(text: str) -> bool:
    return bool(_ANTI_PATTERN.search(text))


def classify_bekanntmachung(text: str) -> BekanntmachungType:
    for bt, pattern in _TYPE_PATTERNS:
        if pattern.search(text):
            return bt
    return BekanntmachungType.OTHER


# ───────────────────────────────────────────────────────────────────────────
# Captcha + Rate-Limit
# ───────────────────────────────────────────────────────────────────────────


async def jittered_sleep(min_s: float | None = None, max_s: float | None = None) -> None:
    delay = random.uniform(
        min_s or settings.PIPELINE_RATE_LIMIT_MIN_SECONDS,
        max_s or settings.PIPELINE_RATE_LIMIT_MAX_SECONDS,
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


def is_session_hint_page(html: str) -> bool:
    """True wenn Sitzungshinweis-Modal noch sichtbar (Cookie nicht akzeptiert)."""
    return "<title>Registerportal | Sitzungshinweis</title>" in html


class CaptchaDetected(RuntimeError):
    """Pipeline pausiert, Notification an Admin."""


# ───────────────────────────────────────────────────────────────────────────
# Result-Parser
# ───────────────────────────────────────────────────────────────────────────


_HRB_PATTERN = re.compile(r"\b(HRB|HRA|GnR|PR|VR)\s*(\d+)\b")
_DATE_PATTERN = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
# "Bundesland Amtsgericht Ort HRB nnnn"
_COURT_LINE = re.compile(
    r"^\s*(?P<land>[\wäöüÄÖÜß ]+?)\s+Amtsgericht\s+(?P<court>[\wäöüÄÖÜß \-./]+?)\s+(HRB|HRA|GnR|PR|VR)\s*(\d+)\s*$",
    re.IGNORECASE,
)
# Firma — Ort (em-dash, en-dash oder bindestrich)
_COMPANY_LINE = re.compile(r"^\s*(?P<name>.+?)\s+[–—\-]\s+(?P<city>.+?)\s*$")


def _parse_item_label(label_text: str) -> dict[str, str | None]:
    """Parse den `<label>`-Text eines Result-Items.

    Format:
        Zeile 1: Bekanntmachungs-Typ (z.B. "Veränderungen Gesellschafterliste")
        Zeile 2: "<Bundesland> Amtsgericht <Ort> HRB <Nummer>"
        Zeile 3: "<Firma> — <Ort>"
    """
    lines = [l.strip() for l in label_text.split("\n") if l.strip()]
    result: dict[str, str | None] = {
        "type_text": None,
        "land": None,
        "register_court": None,
        "hrb_full": None,
        "hrb_nummer": None,
        "company_name": None,
        "company_city": None,
    }

    if not lines:
        return result

    result["type_text"] = lines[0] if lines else None

    # Find court line + company line in remaining
    for line in lines[1:]:
        m = _COURT_LINE.match(line)
        if m:
            result["land"] = m.group("land").strip()
            result["register_court"] = m.group("court").strip()
            result["hrb_nummer"] = m.group(4)
            result["hrb_full"] = f"{m.group(3).upper()} {m.group(4)}"
            continue
        m = _COMPANY_LINE.match(line)
        if m and not result["company_name"]:
            result["company_name"] = m.group("name").strip()
            result["company_city"] = m.group("city").strip()

    # Fallback for HRB if court-line nicht gematcht
    if not result["hrb_nummer"]:
        m = _HRB_PATTERN.search(label_text)
        if m:
            result["hrb_full"] = f"{m.group(1).upper()} {m.group(2)}"
            result["hrb_nummer"] = m.group(2)

    return result


def parse_results_page(
    html: str, *, crawl_run_id: UUID, source: str = "handelsregister.de"
) -> list[BekanntmachungRaw]:
    """Parse alle Bekanntmachungs-Einträge aus der Result-Page-HTML."""
    tree = HTMLParser(html)

    # Datalist-Items: dt enthält Datum, dd alle Bekanntmachungen des Tages
    items: list[BekanntmachungRaw] = []
    list_root = tree.css_first("dl#bekanntMachungenForm\\:datalistId_list")
    if not list_root:
        # Fallback: text-search
        list_root = tree.css_first("dl.ui-datalist-data")
    if not list_root:
        log.warning("no_datalist_in_results")
        return items

    children = list_root.iter()
    current_date: date | None = None
    for child in children:
        if child.tag == "dt":
            # Datum extrahieren
            text = (child.text() or "").strip()
            m = _DATE_PATTERN.search(text)
            if m:
                try:
                    current_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                except ValueError:
                    current_date = None
            continue
        if child.tag != "dd" or current_date is None:
            continue
        # Alle <label>-Elemente in dd → ein Bekanntmachungs-Eintrag pro Label
        for label in child.css("label.ui-outputlabel"):
            label_html = label.html or ""
            # Replace <br> + variants with newline, then strip tags
            label_text = re.sub(r"<br\s*/?>", "\n", label_html, flags=re.IGNORECASE)
            label_text = HTMLParser(label_text).text(separator="\n")

            parsed = _parse_item_label(label_text)
            if not parsed["company_name"]:
                continue

            # Anti-Pattern: Liquidations/Löschungs-Bekanntmachungen direkt filtern
            full_text = (parsed.get("type_text") or "") + " " + label_text
            if is_anti_pattern(full_text):
                continue

            bt = classify_bekanntmachung(parsed.get("type_text") or label_text)

            items.append(
                BekanntmachungRaw(
                    source=source,
                    bekanntmachung_type=bt,
                    hrb_nummer=parsed["hrb_full"],
                    register_court=parsed["register_court"],
                    company_name=parsed["company_name"],
                    company_city=parsed.get("company_city"),
                    country_code=CountryCode.DE,
                    bekanntmachung_date=current_date,
                    raw_text=label_text.strip(),
                    raw_html=(label.html or "")[:3000],
                    parsed_payload={"land": parsed.get("land"), "type_text": parsed.get("type_text")},
                    crawl_run_id=crawl_run_id,
                )
            )

    log.info("results_parsed", count=len(items))
    return items


# ───────────────────────────────────────────────────────────────────────────
# Browser-Context
# ───────────────────────────────────────────────────────────────────────────


async def _new_stealth_context() -> tuple[object, BrowserContext]:
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=settings.HEADLESS,
        user_agent=settings.PIPELINE_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="de-DE",
        timezone_id="Europe/Berlin",
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, context


async def _stealth_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    await _STEALTH.apply_stealth_async(page)
    return page


async def _safe_content(page: Page, retries: int = 3) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return await page.evaluate("() => document.documentElement.outerHTML")
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"page.content failed after {retries} retries: {last_err}")


# ───────────────────────────────────────────────────────────────────────────
# Main Crawler
# ───────────────────────────────────────────────────────────────────────────


async def crawl_bekanntmachungen(
    *,
    crawl_run_id: UUID,
    days_back: int = 7,
    max_pages: int = 1,
) -> AsyncIterator[BekanntmachungRaw]:
    """Crawl handelsregister.de Bekanntmachungen.

    Default-Verhalten zeigt die letzten ~4 Wochen automatisch.
    `days_back` ist Hint für späteren Date-Filter, aktuell nutzen wir Default-View.
    """
    pw, context = await _new_stealth_context()
    try:
        page = await _stealth_page(context)

        # 1. Welcome-Page laden
        log.info("crawl_start", url=HR_WELCOME_URL)
        await page.goto(HR_WELCOME_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector("body", timeout=15_000)
        await asyncio.sleep(2)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        html = await _safe_content(page)
        if is_captcha_page(html):
            log.error("captcha_on_landing")
            raise CaptchaDetected("Captcha auf welcome.xhtml")

        # 2. Sitzungshinweis akzeptieren (falls noch sichtbar)
        if is_session_hint_page(html):
            log.info("accepting_session_hint")
            try:
                await page.locator("a.cookie-btn").first.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception as e:
                log.warning("cookie_button_click_failed", error=str(e))

        await jittered_sleep()

        # 3. Klick auf Bekanntmachungen-Menü-Link
        log.info("navigating_to_bekanntmachungen")
        try:
            await page.locator("#naviForm\\:bekanntmachungenLink").click(timeout=10_000)
        except Exception as e:
            log.error("nav_click_failed", error=str(e))
            raise
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        # Warte auf das Datalist-Element
        try:
            await page.wait_for_selector("dl.ui-datalist-data", timeout=15_000)
        except Exception:
            log.warning("datalist_not_loaded_in_time")

        await jittered_sleep()

        html = await _safe_content(page)
        if is_captcha_page(html):
            log.error("captcha_on_results")
            raise CaptchaDetected("Captcha auf Bekanntmachungs-Seite")

        # 4. Parse
        bekanntmachungen = parse_results_page(
            html, crawl_run_id=crawl_run_id, source="handelsregister.de"
        )

        # Optional: nur die `days_back` Tage rückwirkend
        if days_back is not None and days_back > 0:
            cutoff = date.today().toordinal() - days_back
            bekanntmachungen = [
                b for b in bekanntmachungen if b.bekanntmachung_date.toordinal() >= cutoff
            ]
            log.info("filtered_by_days_back", days_back=days_back, count=len(bekanntmachungen))

        for b in bekanntmachungen:
            yield b

    finally:
        await context.close()
        try:
            await pw.stop()
        except Exception:
            pass
