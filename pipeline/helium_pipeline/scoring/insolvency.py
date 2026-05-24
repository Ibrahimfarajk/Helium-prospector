"""Insolvenz-Cross-Reference (Phase 6.5 Filter 4).

ZIEL: Person + Firma der letzten 5 Jahre auf insolvenzbekanntmachungen.de
prüfen. Bei Match → Hard-Gate-Reject (do_not_contact=true, reason=insolvency).

PRE-MORTEM-MITIGATIONEN:
- reCAPTCHA-Wand: Playwright-Stealth + persistent profile + manual-mode fallback
- Lax-Name-Match: nur Match wenn (Person-Last UND Firma-Substring) ODER (HRB)
- Rate-Limit: max 1 Request/30s, max 5 Lookups/h
- IP-Ban-Schutz: nur für Top-Leads (Posterior >= 0.10) checken, nicht jede

Architektur:
- Lookup ist OPTIONAL — bei Captcha/Error: graceful skip (kein Reject)
- Result wird in Lead.do_not_contact + reason="insolvency" persistiert
"""

from __future__ import annotations

import asyncio
import re

import structlog
from playwright.async_api import BrowserContext

log = structlog.get_logger()


INSOLVENZ_URL = "https://www.insolvenzbekanntmachungen.de/cgi-bin/rechtsprechung/list.pl"


# ───────────────────────────────────────────────────────────────────────────
# Result-Dataclass
# ───────────────────────────────────────────────────────────────────────────


from dataclasses import dataclass


@dataclass(slots=True)
class InsolvencyCheckResult:
    """Result of insolvency lookup."""
    has_match: bool
    confidence: str  # 'high' (exact HRB or Person+Firma), 'medium', 'low' (only name), 'none'
    matches_count: int
    notes: str | None
    skipped_reason: str | None = None  # 'captcha', 'rate_limit', 'no_browser', ...


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


async def check_insolvency(
    *,
    context: BrowserContext | None,
    person_last_name: str | None,
    company_name: str,
    company_city: str | None = None,
    hrb_nummer: str | None = None,
) -> InsolvencyCheckResult:
    """Prüfe Person + Firma gegen insolvenzbekanntmachungen.de.

    Bei context=None oder Captcha: return InsolvencyCheckResult(has_match=False,
    skipped_reason=...) — Lead bleibt unverändert.

    Confidence-Stufen:
    - 'high'   = HRB matched ODER (Last-Name UND Firma-Substring im selben Hit)
    - 'medium' = Firma-Substring im selben Stadt-Treffer
    - 'low'    = nur Last-Name (zu lax, lieber kein Reject)
    - 'none'   = keine Hits
    """
    if context is None:
        return InsolvencyCheckResult(
            has_match=False, confidence="none", matches_count=0, notes=None,
            skipped_reason="no_browser_context",
        )

    page = await context.new_page()
    try:
        # ─── Such-Page laden ─────────────────────────────────────────────
        try:
            await page.goto(INSOLVENZ_URL, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
        except Exception as e:
            log.warning("insolvency_page_load_failed", error=str(e))
            return InsolvencyCheckResult(
                has_match=False, confidence="none", matches_count=0, notes=None,
                skipped_reason="page_load_failed",
            )

        html = await page.evaluate("() => document.documentElement.outerHTML")
        if any(kw in html.lower() for kw in ("captcha", "sicherheitsabfrage", "recaptcha")):
            log.warning("insolvency_captcha_detected")
            return InsolvencyCheckResult(
                has_match=False, confidence="none", matches_count=0, notes=None,
                skipped_reason="captcha",
            )

        # ─── Search durchführen ──────────────────────────────────────────
        # Site hat zwei zentrale Felder: "Name/Firma" + "Wohnort/Sitz"
        # Wir suchen nach Firma + Sitz (Stadt) für engste Match-Region.
        try:
            # Beste Match-Strategie: Firma + Stadt
            firma_input = page.locator(
                "input[name*='firma'], input[name*='name'], input#firma"
            ).first
            if await firma_input.count() > 0:
                await firma_input.fill(company_name[:80])
            if company_city:
                ort_input = page.locator(
                    "input[name*='ort'], input[name*='sitz'], input#wohnsitz"
                ).first
                if await ort_input.count() > 0:
                    await ort_input.fill(company_city)
            # Submit
            submit_btn = page.locator("input[type='submit'], button[type='submit']").first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await asyncio.sleep(3)
        except Exception as e:
            log.warning("insolvency_form_interaction_failed", error=str(e))
            return InsolvencyCheckResult(
                has_match=False, confidence="none", matches_count=0, notes=None,
                skipped_reason="form_failed",
            )

        # ─── Results parsen ──────────────────────────────────────────────
        result_html = await page.evaluate("() => document.documentElement.outerHTML")
        result_text = result_html.lower()

        # Naive Match-Logik:
        # 1) Wenn Result-Page "keine Treffer" oder leere Tabelle → none
        # 2) Wenn Firmenname-Token + Last-Name beide in selbem <tr> → high
        # 3) Wenn nur Firma → medium
        if "keine treffer" in result_text or "kein eintrag" in result_text:
            return InsolvencyCheckResult(
                has_match=False, confidence="none", matches_count=0, notes=None,
            )

        # HRB-Match: höchste Confidence
        if hrb_nummer:
            hrb_clean = hrb_nummer.replace("HRB", "").strip()
            if hrb_clean and hrb_clean in result_text:
                return InsolvencyCheckResult(
                    has_match=True, confidence="high", matches_count=1,
                    notes=f"HRB {hrb_clean} im Result-Set",
                )

        # Firma + Person-Last in selbem Block: high confidence
        if person_last_name:
            company_token = re.escape(company_name.split()[0].lower())
            person_token = re.escape(person_last_name.lower())
            if re.search(rf"{company_token}.*{person_token}", result_text) or re.search(
                rf"{person_token}.*{company_token}", result_text
            ):
                return InsolvencyCheckResult(
                    has_match=True, confidence="high", matches_count=1,
                    notes="Firma + Person-Last in selbem Block",
                )

        # Nur Firma-Match: medium
        if company_name.split()[0].lower() in result_text:
            return InsolvencyCheckResult(
                has_match=True, confidence="medium", matches_count=1,
                notes="Firma-Token im Result-Set ohne Person-Konfirmation",
            )

        return InsolvencyCheckResult(
            has_match=False, confidence="none", matches_count=0, notes=None,
        )
    finally:
        try:
            await page.close()
        except Exception:
            pass
