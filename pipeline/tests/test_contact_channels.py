"""Tests für Phase 6.5 Multi-Channel-Dossier-Extraktion."""

from __future__ import annotations

from helium_pipeline.telephony.phone_finder import (
    extract_contact_channels_from_html,
)


def test_extract_phone_and_email():
    html = """<html><body>
    <h1>Impressum</h1>
    Tel: +49 89 1234567<br>
    E-Mail: max@example.de
    </body></html>"""
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    by_channel = {c.channel: c for c in channels}
    assert "phone" in by_channel
    assert by_channel["phone"].value.startswith("+49")
    assert "email" in by_channel
    assert by_channel["email"].value == "max@example.de"


def test_extract_mobile_higher_confidence():
    html = "<html><body>Mobil: +49 171 1234567 — Tel: +49 89 1234567</body></html>"
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    by_ch = {c.channel: c for c in channels}
    assert "mobile" in by_ch
    assert "phone" in by_ch
    # Mobile hat +0.1 confidence
    assert by_ch["mobile"].confidence > by_ch["phone"].confidence


def test_generic_email_lower_confidence():
    html = """<html><body>
    E-Mail: max.mueller@firma.de — Sekretariat: info@firma.de
    </body></html>"""
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    emails = [c for c in channels if c.channel == "email"]
    assert len(emails) == 2
    by_value = {c.value: c for c in emails}
    # info@ ist generic → niedrigere confidence
    assert by_value["info@firma.de"].confidence < by_value["max.mueller@firma.de"].confidence


def test_extract_linkedin():
    html = """<html><body>
    <a href="https://www.linkedin.com/in/maxmuster">LinkedIn</a>
    </body></html>"""
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    li = [c for c in channels if c.channel == "linkedin"]
    assert len(li) == 1
    assert "maxmuster" in li[0].value


def test_dedupes_phone_within_same_source():
    html = """<html><body>
    Tel: +49 89 1234567
    Tel: +49 89 1234567
    </body></html>"""
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    phones = [c for c in channels if c.channel == "phone"]
    assert len(phones) == 1


def test_ignores_service_numbers():
    html = """<html><body>
    Hotline: 0800 1234567
    </body></html>"""
    channels = extract_contact_channels_from_html(html=html, source_label="test:/")
    assert not any(c.channel in ("phone", "mobile") for c in channels)


def test_empty_html_returns_empty():
    channels = extract_contact_channels_from_html(html="", source_label="test:/")
    assert channels == []
