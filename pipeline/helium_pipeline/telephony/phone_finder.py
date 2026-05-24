"""Telefon-Findung: Firmen-Webseite via Google-Site-Search → Impressum-Parse.

V2.3-Strategie: kein Google-API (kostet). Wir nutzen DuckDuckGo HTML-Search
als gratis Variante, parsen das Impressum/Kontakt-Seite, extrahieren Telefon.

Fallback wenn nicht findbar: Lead bekommt phone=None, Status "Telefon offen".
Closer kann manuell ergänzen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog
import tldextract
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Telefon-Pattern (DACH)
# ───────────────────────────────────────────────────────────────────────────

# Matched:
#   +49 30 123456
#   030 / 12345678
#   030-12345678
#   (030) 12345-678
#   +43 1 1234567
#   +41 44 1234567
_PHONE_PATTERN = re.compile(
    r"""
    (?:
        \+?(?:49|43|41)\s?         # +49 / +43 / +41
        |
        \(?0\d{1,4}\)?              # 0XX area code
    )
    [\s./-]*
    \d{2,4}
    (?:[\s./-]*\d{2,5})+
    """,
    re.VERBOSE,
)


def normalize_phone(raw: str) -> str:
    """Normalize: '+49 (0)89 1234-5678' → '+49 89 1234-5678'"""
    cleaned = raw.strip()
    # remove (0) from internat. notation
    cleaned = re.sub(r"\(0\)", "", cleaned)
    # collapse spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def extract_phone_from_html(html: str) -> str | None:
    text = HTMLParser(html).text(separator="\n")
    m = _PHONE_PATTERN.search(text)
    if not m:
        return None
    return normalize_phone(m.group(0))


# ───────────────────────────────────────────────────────────────────────────
# Domain-Discovery via DuckDuckGo
# ───────────────────────────────────────────────────────────────────────────


DDG_URL = "https://html.duckduckgo.com/html/"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=8), reraise=True)
async def find_company_domain(
    *,
    company_name: str,
    city: str | None,
    client: httpx.AsyncClient,
) -> str | None:
    """Gibt z.B. 'example.de' zurück, oder None."""
    q = company_name
    if city:
        q = f"{q} {city}"
    q = f"{q} impressum"

    try:
        resp = await client.post(
            DDG_URL,
            data={"q": q},
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("ddg_search_fail", error=str(e))
        return None

    tree = HTMLParser(resp.text)
    # DDG result links — wir nehmen das erste, das nach DACH-Domain aussieht
    for link in tree.css("a.result__a"):
        href = link.attributes.get("href") or ""
        if not href:
            continue
        try:
            ext = tldextract.extract(href)
        except Exception:
            continue
        blocked = {
            # Verzeichnisse / Aggregatoren
            "linkedin", "xing", "northdata", "kompass", "facebook",
            "cylex", "implisense", "creditsafe", "companyhouse",
            "wer-zu-wem", "bisnode", "ec", "duckduckgo",
            "yelp", "gelbeseiten", "11880", "dasoertliche", "branchenbuch",
            # Register / Behörden
            "handelsregister", "handelsregisterbekanntmachungen",
            "unternehmensregister", "bundesanzeiger", "bafin",
            "ihk", "destatis", "europa", "transparenzregister",
            # Wirtschaftsauskunft
            "creditreform", "schufa", "kapital", "boniforce", "moodys",
            # Presse / News
            "presseportal", "finanznachrichten", "wallstreet-online",
        }
        if ext.suffix in {"de", "at", "ch", "com"} and ext.domain not in blocked:
            return f"{ext.domain}.{ext.suffix}"

    return None


# ───────────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class PhoneResult:
    phone: str | None
    source: str | None
    website: str | None


async def find_phone(
    *,
    company_name: str,
    city: str | None,
    client: httpx.AsyncClient,
) -> PhoneResult:
    """Versuche Telefon zu finden. Mehrere Fallbacks.

    1. DDG-Search → Firmen-Domain → /impressum lesen → Telefon extrahieren
    2. DDG-Search → Domain → Startseite lesen → Telefon extrahieren
    3. Keine Phone → return None, Lead bleibt anrufbar via manual lookup
    """
    domain = await find_company_domain(
        company_name=company_name, city=city, client=client
    )
    if not domain:
        return PhoneResult(phone=None, source=None, website=None)

    # Versuche /impressum oder /kontakt
    for path in ("/impressum", "/kontakt", "/imprint", "/legal-notice", "/"):
        url = f"https://{domain}{path}"
        try:
            resp = await client.get(url, timeout=10.0, follow_redirects=True)
            if resp.status_code != 200:
                continue
            phone = extract_phone_from_html(resp.text)
            if phone:
                return PhoneResult(
                    phone=phone, source=f"firmen-impressum:{domain}{path}", website=domain
                )
        except httpx.HTTPError as e:
            log.debug("impressum_fetch_fail", domain=domain, path=path, error=str(e))
            continue

    return PhoneResult(phone=None, source=None, website=domain)
