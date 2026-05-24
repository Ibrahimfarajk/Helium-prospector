"""Reachability-Engine (Phase 8.2 A1).

ZIEL: misst ob Closer den Lead operativ erreichen kann — nicht ob er wahrscheinlich
kauft. Konzernzentrale = Posterior-Killer, Inhaber-Durchwahl = Boost.

Eingabe: list[ContactChannel] aus phone_finder.find_all_contact_channels.
Wenn leer: Flag `no_reachability_data=True` → kein Multiplikator (×1.0).

Signale & Multiplikatoren (alle Phase-8.2-Startwerte):
- has_direct_line       : ×2.5   (Durchwahl oder Mobil im Impressum)
- has_personal_email    : ×1.8   (Persona-Mail wie m.mueller@firma.de)
- inhaber_gefuehrt      : ×1.5   (kleine GmbH-Indikatoren)
- large_corporate_switch: ×0.5   (Konzernzentrale-Pattern, Penalty)

Cluster-Cap: alle gehören Familie "reachability" — within-family wird gedimmt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Confidence-Source-Tracking (1-3 Sterne im Dashboard)
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ReachabilityResult:
    """Eingang in Bayes als Reachability-LRs."""

    lrs: dict[str, float] = field(default_factory=dict)
    """Map {reachability_<signal>: lr_value}."""

    confidence: dict[str, int] = field(default_factory=dict)
    """Map {signal: stars 1-3} für Dashboard-Visualisierung."""

    no_reachability_data: bool = False
    """True wenn keine contact_channels vorlagen → kein Multiplikator."""

    notes: list[str] = field(default_factory=list)
    """Audit-Trail: warum welches Signal gefeuert hat."""


# ───────────────────────────────────────────────────────────────────────────
# Pattern-Detection
# ───────────────────────────────────────────────────────────────────────────

# Persona-E-Mail-Whitelist: alles was wie ein Vor-/Nachname aussieht
# Beispiele die matchen sollen: max.mustermann@, m.mustermann@, mmuster@,
#                                mueller-schmidt@, dr.mueller@
# Beispiele die NICHT matchen sollen: info@, kontakt@, office@, vertrieb@,
#                                      team@, sales@, marketing@, webmaster@,
#                                      noreply@, admin@, buero@, service@
_GENERIC_INBOX_BLACKLIST = {
    "info", "kontakt", "office", "vertrieb", "team", "sales", "marketing",
    "webmaster", "noreply", "admin", "buero", "service", "mail", "hallo",
    "anfrage", "support", "presse", "karriere", "jobs", "shop",
    "newsletter", "abo", "verwaltung", "empfang", "rezeption",
}

_PERSONA_TOKEN = re.compile(
    r"^([a-z]+(?:[.\-_][a-z]+)+|[a-z]\.[a-z]+|[a-z]{4,})$"
)


def is_persona_email(email: str) -> bool:
    """True wenn die E-Mail-Local-Part wie ein Personenname aussieht."""
    local = email.split("@", 1)[0].lower().strip()
    if local in _GENERIC_INBOX_BLACKLIST:
        return False
    # Heuristik: Vor.Nach oder V.Nach oder Vorname-Nachname Pattern
    if not _PERSONA_TOKEN.match(local):
        return False
    # Doppel-Check: enthält ein "Trenn-Zeichen" (Punkt, Bindestrich, Unterstrich)
    # ODER ist >=6 Zeichen lang (zb "mueller", "fischer")
    has_separator = any(sep in local for sep in (".", "-", "_"))
    if has_separator:
        return True
    if len(local) >= 6:
        return True
    return False


def is_direct_line(phone: str) -> bool:
    """True wenn Telefon wie eine Durchwahl/Mobil aussieht (nicht Zentrale)."""
    digits = re.sub(r"[^\d]", "", phone)
    # Mobile DE/AT/CH (0151-0179, +491xx)
    if re.match(r"^(?:49|43|41)?0?1[567]\d", digits):
        return True
    # Durchwahl-Indikator: Bindestrich nach Vorwahl mit konkretem Suffix
    # +49 89 1234-567 (mit Trenner) → Durchwahl
    if re.search(r"[-/]\d{2,4}\s*$", phone):
        return True
    return False


# Konzern-/Switchboard-Pattern in der Source-Beschreibung
_LARGE_SWITCH_PATTERNS = [
    re.compile(r"\b(?:konzern|holding|gruppe|group)[\s-]?(?:zentrale|sitz)\b", re.IGNORECASE),
    re.compile(r"\bhauptverwaltung\b", re.IGNORECASE),
    re.compile(r"\bcenter[\s-]?of[\s-]?expertise\b", re.IGNORECASE),
]

# Inhaber-Indikatoren in Source-Beschreibung
_INHABER_HINTS = [
    re.compile(r"\binhaber(?:in)?\b", re.IGNORECASE),
    re.compile(r"\bgesch[äa]ftsinhaber\b", re.IGNORECASE),
    re.compile(r"\beigent[üu]mer[- ]?gef[üu]hrt", re.IGNORECASE),
]


# ───────────────────────────────────────────────────────────────────────────
# Hauptfunktion
# ───────────────────────────────────────────────────────────────────────────

# LR-Tabelle (Startwerte aus Phase-8.2-Auftrag, im Bayes-Modul gespiegelt)
REACHABILITY_LRS = {
    "reachability_direct_line": 2.5,
    "reachability_personal_email": 1.8,
    "reachability_inhaber_gefuehrt": 1.5,
    "reachability_large_corporate_switchboard": 0.5,
}


def assess_reachability(
    *,
    contact_channels: list[dict[str, Any]] | None,
    company_name: str | None = None,
    company_size_class: str | None = None,
    impressum_text: str | None = None,
) -> ReachabilityResult:
    """Bewerte Reachability auf Basis bestehender contact_channels.

    Args:
        contact_channels: Output von phone_finder.find_all_contact_channels
            (Liste von dicts: {channel, value, source, confidence, notes}).
        company_name: für Pattern-Match (z.B. "AG", "SE" → eher Konzern).
        company_size_class: aus anti_filters.classify_size — wenn "klein"/"kleinst"
            → inhabergeführt-Indikator (Bestätigung).
        impressum_text: optionaler Volltext für Inhaber-Hint-Match.

    Returns:
        ReachabilityResult mit lrs, confidence, no_reachability_data.
    """
    result = ReachabilityResult()

    if not contact_channels:
        result.no_reachability_data = True
        result.notes.append("no_contact_channels — no reachability multiplier")
        return result

    # Aggregiere pro Kanal-Typ
    phones = [c for c in contact_channels if c.get("channel") in ("phone", "mobile")]
    emails = [c for c in contact_channels if c.get("channel") == "email"]

    # ── Signal 1: has_direct_line ──────────────────────────────────────
    direct_line_sources = 0
    for p in phones:
        if is_direct_line(p.get("value", "")):
            direct_line_sources += 1

    if direct_line_sources:
        result.lrs["reachability_direct_line"] = REACHABILITY_LRS["reachability_direct_line"]
        result.confidence["direct_line"] = min(3, direct_line_sources)
        result.notes.append(f"direct_line in {direct_line_sources} channel(s)")

    # ── Signal 2: has_personal_email ───────────────────────────────────
    persona_email_sources = 0
    for e in emails:
        if is_persona_email(e.get("value", "")):
            persona_email_sources += 1

    if persona_email_sources:
        result.lrs["reachability_personal_email"] = REACHABILITY_LRS["reachability_personal_email"]
        result.confidence["personal_email"] = min(3, persona_email_sources)
        result.notes.append(f"persona_email in {persona_email_sources} channel(s)")

    # ── Signal 3: inhaber_gefuehrt ─────────────────────────────────────
    # Drei Confidence-Levels:
    # *   Size-Class "kleinst" allein (1 Stern)
    # **  Size-Class + Impressum-Hint (2 Sterne)
    # *** Size-Class + Impressum-Hint + persona_email (3 Sterne)
    inhaber_hits = 0
    if company_size_class in ("kleinst", "klein"):
        inhaber_hits += 1
    if impressum_text:
        if any(p.search(impressum_text) for p in _INHABER_HINTS):
            inhaber_hits += 1
    if persona_email_sources > 0:
        inhaber_hits += 1

    if inhaber_hits >= 1:
        result.lrs["reachability_inhaber_gefuehrt"] = REACHABILITY_LRS["reachability_inhaber_gefuehrt"]
        result.confidence["inhaber_gefuehrt"] = min(3, inhaber_hits)
        result.notes.append(f"inhaber_gefuehrt confidence {inhaber_hits}/3")

    # ── Signal 4: large_corporate_switchboard (Penalty) ────────────────
    is_corporate = False
    if company_name:
        # AG/SE deuten auf größere Strukturen — aber nicht hart blocken
        if re.search(r"\b(?:AG|SE|S\.E\.|Aktiengesellschaft|Konzern)\b", company_name):
            is_corporate = True
    if impressum_text:
        if any(p.search(impressum_text) for p in _LARGE_SWITCH_PATTERNS):
            is_corporate = True
    # Wenn KEIN direct_line gefunden UND >=3 generic-emails → Konzern-Indikator
    generic_email_count = sum(
        1 for e in emails if not is_persona_email(e.get("value", ""))
    )
    if direct_line_sources == 0 and generic_email_count >= 3:
        is_corporate = True

    if is_corporate:
        # Penalty nur wenn KEIN starkes positives Reachability-Signal da ist
        # — sonst widersprechen wir uns selbst.
        if not result.lrs:
            result.lrs["reachability_large_corporate_switchboard"] = (
                REACHABILITY_LRS["reachability_large_corporate_switchboard"]
            )
            result.confidence["large_corporate_switchboard"] = 2
            result.notes.append("corporate_pattern + no positive signal")

    return result
