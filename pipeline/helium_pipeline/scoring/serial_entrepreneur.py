"""Serien-Unternehmer-Detection (Phase 6.5 F2).

ZIEL: Wenn eine Person als GF/Anteilseigner an >=3 Firmen aktiv ist
→ STARKES Signal für "Serien-Unternehmer / HNW-Profil".

ARCHITEKTUR:
- Quelle 1: handelsregister.de Personensuche (kostenlos, public)
- Quelle 2: WpHG-Stimmrechtsmitteilungen (BaFin) — Stub-Plug, später aktivierbar
- Cache mit 30d-TTL — Personen-Mappings ändern sich selten

PRE-MORTEM-MITIGATIONEN:
- Lookup ist OPTIONAL — bei Captcha/Error gracefull skip (kein Penalty)
- Rate-Limit: pipeline-seitig max 1 Lookup/30s
- IP-Ban-Schutz: nur für Top-Leads (Posterior ≥ 0.05 vor F2-Lookup)
- Cache wird auf Disk in ~/.helium-pipeline/person-cache/<hash>.json gespeichert
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from playwright.async_api import BrowserContext

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Cache
# ───────────────────────────────────────────────────────────────────────────

_CACHE_DIR = Path.home() / ".helium-pipeline" / "person-cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL = timedelta(days=30)


def _cache_key(first: str | None, last: str) -> str:
    key = f"{(first or '').strip().lower()}|{last.strip().lower()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _cache_path(first: str | None, last: str) -> Path:
    return _CACHE_DIR / f"{_cache_key(first, last)}.json"


def _read_cache(first: str | None, last: str) -> "SerialEntrepreneurResult | None":
    p = _cache_path(first, last)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(d["cached_at"])
        if datetime.now(UTC) - ts > _CACHE_TTL:
            return None
        return SerialEntrepreneurResult(
            count=d["count"],
            companies=d["companies"],
            cached=True,
            source=d.get("source", "cache"),
            skipped_reason=None,
        )
    except Exception:
        return None


def _write_cache(first: str | None, last: str, result: "SerialEntrepreneurResult") -> None:
    p = _cache_path(first, last)
    try:
        p.write_text(
            json.dumps(
                {
                    "cached_at": datetime.now(UTC).isoformat(),
                    "count": result.count,
                    "companies": result.companies,
                    "source": result.source,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning("serial_cache_write_failed", error=str(e))


# ───────────────────────────────────────────────────────────────────────────
# Result-Dataclass
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SerialEntrepreneurResult:
    count: int
    companies: list[str]
    cached: bool = False
    source: str = "handelsregister"
    skipped_reason: str | None = None


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────

HR_PERSON_URL = "https://www.handelsregister.de/rp_web/normalesuche.xhtml"


async def lookup_person_serial(
    *,
    context: BrowserContext | None,
    first_name: str | None,
    last_name: str,
    exclude_company: str | None = None,
) -> SerialEntrepreneurResult:
    """Hole Anzahl Firmen wo diese Person als GF/Anteilseigner registriert ist.

    Args:
        exclude_company: Firma die ausgeschlossen wird (die aktuelle Lead-Firma)

    Bei context=None / Captcha / Error: skipped_reason gesetzt, count=0.
    """
    # 1. Cache-Check
    cached = _read_cache(first_name, last_name)
    if cached is not None:
        if exclude_company:
            cached.companies = [c for c in cached.companies if exclude_company.lower() not in c.lower()]
            cached.count = len(cached.companies)
        return cached

    if context is None:
        return SerialEntrepreneurResult(
            count=0, companies=[], skipped_reason="no_browser_context",
        )

    page = await context.new_page()
    try:
        try:
            await page.goto(HR_PERSON_URL, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("hr_person_page_load_failed", error=str(e))
            return SerialEntrepreneurResult(
                count=0, companies=[], skipped_reason="page_load_failed",
            )

        html = await page.evaluate("() => document.documentElement.outerHTML")
        if any(kw in html.lower() for kw in ("captcha", "sicherheitsabfrage", "recaptcha")):
            log.warning("hr_person_captcha")
            return SerialEntrepreneurResult(
                count=0, companies=[], skipped_reason="captcha",
            )

        # PrimeFaces — feld-IDs sind versionsabhängig, lookup via label
        try:
            # Erweiterte Suche → Person-Reiter falls vorhanden
            person_tab = page.locator(
                "a:has-text('Suche nach Person'), a:has-text('Person')"
            ).first
            if await person_tab.count() > 0:
                await person_tab.click()
                await asyncio.sleep(1)

            # Last-Name-Input
            last_input = page.locator(
                "input[id*='nachname'], input[name*='nachname'], input[id*='name']"
            ).first
            if await last_input.count() > 0:
                await last_input.fill(last_name)
            if first_name:
                first_input = page.locator(
                    "input[id*='vorname'], input[name*='vorname']"
                ).first
                if await first_input.count() > 0:
                    await first_input.fill(first_name)

            submit = page.locator(
                "button:has-text('Suchen'), input[type='submit'][value*='Suchen']"
            ).first
            if await submit.count() > 0:
                await submit.click()
                await asyncio.sleep(4)
        except Exception as e:
            log.warning("hr_person_form_failed", error=str(e))
            return SerialEntrepreneurResult(
                count=0, companies=[], skipped_reason="form_failed",
            )

        # Result parsen: jede Zeile mit "GmbH"/"AG"/"UG"/"KG" ist ein Hit
        result_html = await page.evaluate("() => document.documentElement.outerHTML")
        companies = _extract_companies_from_result(result_html, exclude_company)

        result = SerialEntrepreneurResult(
            count=len(companies),
            companies=companies,
            cached=False,
            source="handelsregister",
        )
        _write_cache(first_name, last_name, result)
        return result

    finally:
        try:
            await page.close()
        except Exception:
            pass


_COMPANY_LINE = re.compile(
    r"\b([A-ZÄÖÜ][\w\s\.\-&,]{2,80}?(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|UG\s*\(haftungsbeschr[äa]nkt\)|AG|KG|e\.K\.|OHG|Limited|Ltd\.?))",
)


def _extract_companies_from_result(html: str, exclude: str | None = None) -> list[str]:
    """Heuristik-Extraction: ziehe alle GmbH/AG/UG/KG-Firmenamen aus dem HTML."""
    from selectolax.parser import HTMLParser

    try:
        text = HTMLParser(html).text(separator="\n")
    except Exception:
        text = html

    found: set[str] = set()
    for m in _COMPANY_LINE.finditer(text):
        nm = m.group(1).strip()
        # nichtssagende Treffer raus
        if len(nm) < 6 or len(nm) > 80:
            continue
        if exclude and exclude.lower() in nm.lower():
            continue
        found.add(nm)
    return sorted(found)
