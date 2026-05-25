"""Pure-Function-Tests für IO-Module die 0% Coverage hatten.

Diese Module machen externe HTTP/Playwright-Calls — wir testen nur die
synchronen Pure-Functions (Parser, Normalisierer, Cache-Keys).
"""

from __future__ import annotations

import pytest

from helium_pipeline.scoring.online_presence import _is_aggregator
from helium_pipeline.scoring.serial_entrepreneur import (
    _cache_key,
    _extract_companies_from_result,
)
from helium_pipeline.telephony.phone_finder import (
    extract_phone_from_html,
    is_service_number,
    normalize_phone,
)


# ───────────────────────────────────────────────────────────────────────────
# online_presence._is_aggregator
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("host", [
    "www.linkedin.com",
    "xing.com",
    "kompass.de",
    "northdata.de",
    "creditsafe.de",
    "gelbeseiten.de",
    "11880.com",
    "moneyhouse.ch",
])
def test_aggregator_known_blocklist(host):
    assert _is_aggregator(host)


@pytest.mark.parametrize("host", [
    "kleine-gmbh.de",
    "musterfirma.de",
    "company.com",
    "industrie-mueller.de",
])
def test_aggregator_normal_company_domain(host):
    assert not _is_aggregator(host)


# ───────────────────────────────────────────────────────────────────────────
# serial_entrepreneur._cache_key + _extract_companies_from_result
# ───────────────────────────────────────────────────────────────────────────


def test_cache_key_deterministic():
    k1 = _cache_key("Max", "Mustermann")
    k2 = _cache_key("Max", "Mustermann")
    assert k1 == k2
    assert len(k1) == 16


def test_cache_key_case_insensitive():
    assert _cache_key("Max", "Mustermann") == _cache_key("MAX", "MUSTERMANN")
    assert _cache_key("max", "mustermann") == _cache_key("Max", "Mustermann")


def test_cache_key_changes_with_name():
    k1 = _cache_key("Max", "Mustermann")
    k2 = _cache_key("Max", "Mueller")
    assert k1 != k2


def test_cache_key_first_optional():
    k1 = _cache_key(None, "Mustermann")
    k2 = _cache_key("", "Mustermann")
    assert k1 == k2


def test_extract_companies_basic_html():
    html = """
    <html><body>
    <a href="/r/123">Musterfirma GmbH</a>
    <a href="/r/124">Schmidt Beteiligungs GmbH & Co. KG</a>
    <a href="/r/125">Test AG</a>
    </body></html>
    """
    companies = _extract_companies_from_result(html)
    # Expect at least one GmbH or AG match
    matched = " ".join(companies)
    assert "GmbH" in matched or "AG" in matched


def test_extract_companies_excludes_target():
    html = '<a href="/x">Musterfirma GmbH</a><a href="/y">Mustermann Holding GmbH</a>'
    companies = _extract_companies_from_result(html, exclude="Musterfirma")
    assert not any("Musterfirma" in c for c in companies)


def test_extract_companies_empty_html():
    assert _extract_companies_from_result("") == []
    assert _extract_companies_from_result("<html></html>") == []


# ───────────────────────────────────────────────────────────────────────────
# phone_finder pure functions
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected_starts", [
    ("+49 (0)89 1234-5678", "+49"),
    ("+49 89 1234-5678", "+49"),
    ("089 1234 5678", "089"),
])
def test_normalize_phone_basic(raw, expected_starts):
    n = normalize_phone(raw)
    assert n.startswith(expected_starts)


def test_normalize_phone_strips_zero_in_parens():
    """+49 (0)89 → +49 89."""
    n = normalize_phone("+49 (0)89 1234")
    assert "(0)" not in n


def test_normalize_phone_collapses_whitespace():
    n = normalize_phone("+49   89   1234")
    assert "  " not in n  # no double-space


@pytest.mark.parametrize("phone,expected", [
    ("0800 123456", True),
    ("+49 800 123456", True),
    ("0180 123456", True),
    ("0900 123456", True),
    ("+49 89 1234567", False),
    ("030 5550000", False),
    ("+49 171 1234567", False),  # mobile
])
def test_is_service_number(phone, expected):
    assert is_service_number(phone) == expected


def test_extract_phone_from_html_finds_first_valid():
    html = """
    <html><body>
    Hotline: 0800 999888
    Telefon: +49 89 1234567
    </body></html>
    """
    phone = extract_phone_from_html(html)
    assert phone is not None
    assert "0800" not in phone  # Service-Hotline ausgefiltert


def test_extract_phone_skips_too_short():
    html = "<p>Tel: 030 12</p>"
    assert extract_phone_from_html(html) is None  # zu kurz


def test_extract_phone_empty_html():
    assert extract_phone_from_html("") is None
