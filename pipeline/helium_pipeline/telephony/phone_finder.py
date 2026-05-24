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
    cleaned = re.sub(r"\(0\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


_SERVICE_PREFIXES = re.compile(
    r"\b0?(800|180|137|185|190|900|137)\b"  # Service-/Sondernummern
)


def is_service_number(phone: str) -> bool:
    """0800/0180/0900-Hotlines — keine echten Firmen-Kontakte."""
    digits = re.sub(r"[^\d]", "", phone)
    # Sicherheitsabfrage: nach Country-Code 49 die nächsten 3 Ziffern
    if digits.startswith("49"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    return bool(re.match(r"(800|180|137|185|190|900)", digits))


def extract_phone_from_html(html: str) -> str | None:
    text = HTMLParser(html).text(separator="\n")
    # Sammle alle Treffer, nicht nur den ersten
    candidates = [m.group(0) for m in _PHONE_PATTERN.finditer(text)]
    for raw in candidates:
        norm = normalize_phone(raw)
        if is_service_number(norm):
            continue
        # Min 7 digits nach country code (echte Anschlüsse)
        digit_only = re.sub(r"[^\d]", "", norm)
        if len(digit_only) < 9:
            continue
        return norm
    return None


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
            "firmenwissen", "moneyhouse", "krankenkassen-zentrale",
            # Register / Behörden
            "handelsregister", "handelsregisterbekanntmachungen",
            "unternehmensregister", "bundesanzeiger", "bafin",
            "ihk", "destatis", "europa", "transparenzregister",
            "amtsgericht", "justiz", "bundesregierung",
            # Stadt-Behörden / 0800-Hotlines
            "muenchen", "munich", "hamburg", "berlin", "frankfurt", "koeln",
            "stuttgart", "duesseldorf", "leipzig", "dresden", "hannover",
            "bremen", "nuernberg", "essen", "dortmund", "service-bw",
            # Wirtschaftsauskunft
            "creditreform", "schufa", "kapital", "boniforce", "moodys",
            "dnb", "bisnode", "experian",
            # Presse / News / Aktien-Sites
            "presseportal", "finanznachrichten", "wallstreet-online",
            "ariva", "onvista", "boerse", "finanzen", "boersennews",
            # Bürgschaftsbanken / Kammern
            "baybg", "buergschaftsbank", "handwerkskammer",
            # Social
            "twitter", "x", "instagram", "tiktok", "youtube",
            # Generic Software-Provider-Footer
            "wordpress", "wix", "jimdo", "shopify",
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


# ───────────────────────────────────────────────────────────────────────────
# Phase 6.5: Multi-Channel-Extraction
# ───────────────────────────────────────────────────────────────────────────


_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_LINKEDIN_PATTERN = re.compile(
    r"https?://(?:www\.|de\.)?linkedin\.com/(?:in|company)/[\w\-_%]+",
    re.IGNORECASE,
)
_XING_PATTERN = re.compile(
    r"https?://(?:www\.)?xing\.com/(?:profile|companies)/[\w\-_%]+",
    re.IGNORECASE,
)

# Generic Inbox-Patterns absteigend nach "Persönlichkeits-Wert"
_GENERIC_EMAIL_TOKENS = ("info@", "kontakt@", "office@", "kanzlei@", "service@", "mail@", "buero@")


def extract_contact_channels_from_html(
    *, html: str, source_label: str, base_confidence: float = 0.7
) -> list:
    """Extrahiere phone + email + linkedin + xing aus einem Impressum/Kontakt-HTML.

    Returns list[ContactChannel].
    """
    from ..models import ContactChannel

    text = HTMLParser(html).text(separator="\n")
    channels: list = []

    # Phones (mehrere möglich: Zentrale + Mobile)
    seen_phones: set[str] = set()
    for m in _PHONE_PATTERN.finditer(text):
        raw = m.group(0)
        norm = normalize_phone(raw)
        if norm in seen_phones:
            continue
        seen_phones.add(norm)
        if is_service_number(norm):
            continue
        digit_only = re.sub(r"[^\d]", "", norm)
        if len(digit_only) < 9:
            continue
        # Mobile-Heuristik: 015x/016x/017x → mobile, sonst phone
        is_mobile = bool(re.match(r"\+?49?\s?0?1[567]", norm))
        channels.append(ContactChannel(
            channel="mobile" if is_mobile else "phone",
            value=norm,
            source=source_label,
            confidence=base_confidence + (0.1 if is_mobile else 0),
        ))

    # Emails — generic-Inboxen niedrigere Confidence
    seen_emails: set[str] = set()
    for m in _EMAIL_PATTERN.finditer(text):
        em = m.group(0).lower()
        if em in seen_emails:
            continue
        seen_emails.add(em)
        is_generic = any(em.startswith(t) for t in _GENERIC_EMAIL_TOKENS)
        channels.append(ContactChannel(
            channel="email",
            value=em,
            source=source_label,
            confidence=base_confidence - 0.2 if is_generic else base_confidence,
            notes="generic inbox" if is_generic else None,
        ))

    # LinkedIn / Xing nur im HTML matchen, nicht im text (URLs überleben Text-Strip oft nicht)
    for url in _LINKEDIN_PATTERN.findall(html):
        channels.append(ContactChannel(
            channel="linkedin", value=url, source=source_label, confidence=0.4,
        ))
    for url in _XING_PATTERN.findall(html):
        channels.append(ContactChannel(
            channel="xing", value=url, source=source_label, confidence=0.4,
        ))

    return channels


async def find_all_contact_channels(
    *,
    company_name: str,
    city: str | None,
    client: httpx.AsyncClient,
) -> list:
    """Phase 6.5: Multi-Channel-Lookup. Returns list[ContactChannel] sortiert by confidence DESC.

    Scrapes /impressum + /kontakt der Firmen-Domain → extrahiert alle gefundenen Channels.
    """
    domain = await find_company_domain(
        company_name=company_name, city=city, client=client
    )
    if not domain:
        return []

    all_channels = []
    visited_paths: set[str] = set()
    for path in ("/impressum", "/kontakt", "/imprint", "/legal-notice", "/"):
        if path in visited_paths:
            continue
        visited_paths.add(path)
        url = f"https://{domain}{path}"
        try:
            resp = await client.get(url, timeout=10.0, follow_redirects=True)
            if resp.status_code != 200:
                continue
            channels = extract_contact_channels_from_html(
                html=resp.text,
                source_label=f"impressum:{domain}{path}",
                base_confidence=0.85 if path in ("/impressum", "/imprint") else 0.65,
            )
            all_channels.extend(channels)
        except httpx.HTTPError:
            continue

    # Add Website-Domain als eigenen Channel
    if domain:
        from ..models import ContactChannel
        all_channels.append(ContactChannel(
            channel="website",
            value=f"https://{domain}",
            source="ddg-domain-lookup",
            confidence=0.6,
        ))

    # Dedup by (channel, value)
    seen: set[tuple[str, str]] = set()
    deduped = []
    for c in all_channels:
        key = (c.channel, c.value.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    # Sort: confidence DESC, dann channel-priority (phone > mobile > email > linkedin > xing > website)
    priority = {"phone": 5, "mobile": 4, "email": 3, "linkedin": 2, "xing": 1, "website": 0}
    deduped.sort(key=lambda c: (-c.confidence, -priority.get(c.channel, 0)))
    return deduped
