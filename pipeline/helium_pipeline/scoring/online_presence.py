"""Online-Präsenz-Check (Phase 6.5 Filter 6, SOFT).

Heuristik: Eine GmbH mit echter Geschäftstätigkeit hat irgendeine
öffentliche Web-Spur. KEINE Spur → SOFT-Penalty (×0.5 LR), NICHT Reject
— sonst killen wir Stealth-Wealth-HNW false-positives.

Quellen-Check:
1) Firma + Stadt in DuckDuckGo → mind. 1 nicht-Aggregator-Hit
2) (optional) Eigene Domain via tldextract → ist nicht-aggregator-Domain

Rate-Limit: max 1 Lookup pro 5s. Wird nur für T2+ Leads gemacht
(T3 würde Pipeline blockieren).
"""

from __future__ import annotations

import httpx
import structlog
from selectolax.parser import HTMLParser

log = structlog.get_logger()


_DDG_URL = "https://html.duckduckgo.com/html/"

# Aggregator-Domains die NICHT als "Online-Präsenz" zählen
_AGGREGATOR_DOMAINS = {
    "northdata", "handelsregister", "unternehmensregister",
    "bundesanzeiger", "kompass", "wer-zu-wem", "implisense",
    "creditsafe", "cylex", "companyhouse", "firmen", "moneyhouse",
    "openregister", "offeneregister", "openrocket",
    "linkedin", "xing", "facebook", "twitter", "x.com",
    "gelbeseiten", "11880", "dasoertliche", "branchenbuch",
}


def _is_aggregator(host: str) -> bool:
    h = host.lower()
    return any(agg in h for agg in _AGGREGATOR_DOMAINS)


async def has_online_presence(
    *,
    company_name: str,
    city: str | None,
    client: httpx.AsyncClient,
    timeout_s: float = 10.0,
) -> bool:
    """True wenn min. 1 nicht-Aggregator-Hit in DDG-Suche.

    Graceful fallback: bei DDG-Fehler return True (kein Penalty),
    um Stealth-Wealth-HNW nicht versehentlich zu verlieren.
    """
    q = company_name
    if city:
        q = f'"{company_name}" {city}'
    try:
        resp = await client.post(
            _DDG_URL,
            data={"q": q},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
    except Exception as e:
        log.debug("online_presence_check_skipped", error=str(e))
        return True  # graceful: kein Penalty bei DDG-Fail

    tree = HTMLParser(resp.text)
    hits = 0
    for link in tree.css("a.result__a, a.result__url"):
        href = link.attributes.get("href") or ""
        if not href.startswith("http"):
            continue
        # Strip uddg= redirector
        if "uddg=" in href:
            import urllib.parse
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = (parsed.get("uddg") or [""])[0]
        try:
            from urllib.parse import urlparse
            host = urlparse(href).hostname or ""
        except Exception:
            continue
        if host and not _is_aggregator(host):
            hits += 1
            if hits >= 1:
                return True

    return False
