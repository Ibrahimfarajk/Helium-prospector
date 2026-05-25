"""1-Seite-Dossier-Generator (V2.3).

Erzeugt für jeden Lead ein Markdown-Dokument, das vom Closer in 90 Sekunden
gescannt werden kann.

Format-Spec aus RECHERCHE_ANALYSE.md §2.5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models import (
    BekanntmachungRaw,
    BekanntmachungType,
    CompanyEnrichment,
    PersonInfo,
    ScoreBreakdown,
)

# ───────────────────────────────────────────────────────────────────────────
# Best-Call-Window pro Persona-Typ
# ───────────────────────────────────────────────────────────────────────────


def best_call_window(trigger_type: BekanntmachungType, person_role: str | None) -> str:
    """Empfehle Anruf-Zeitfenster basierend auf Persona."""
    role_lower = (person_role or "").lower()
    # Heilberufe: Sprechzeiten meiden
    if any(kw in role_lower for kw in ("arzt", "ärzt", "aerzt", "dr. med", "tierarzt", "zahnarzt", "apotheker")):
        return "Mo–Fr 11:00–13:00 oder 17:00–19:00 (außerhalb Sprechzeiten)"
    # Default GmbH-GF / Geschäftsführer / Vorstand / Gesellschafter
    return "Di/Mi 10:00–12:00 oder 14:30–16:00"


# ───────────────────────────────────────────────────────────────────────────
# Hook-Generierung pro Trigger-Typ
# ───────────────────────────────────────────────────────────────────────────


HOOK_TEMPLATES: dict[BekanntmachungType, str] = {
    BekanntmachungType.SHAREHOLDER_CHANGE: (
        "Frischer Anteilseignerwechsel (HRB {hrb}) — neuer "
        "Liquiditätszufluss wahrscheinlich. Idealer Anschluss: „Sie haben "
        "sich gerade neu ausgerichtet — Wiederanlage-Thema steht auf der "
        "Agenda."
    ),
    BekanntmachungType.GF_CHANGE: (
        "Geschäftsführer-Wechsel (HRB {hrb}) — entweder Exit-Indikator oder "
        "Generations-Übergang. Anschluss: „Bei strukturellen Veränderungen "
        "stellen sich häufig auch Investment-Allokations-Fragen."
    ),
    BekanntmachungType.NEW_REGISTRATION: (
        "Neueintragung — bei Holding-Pattern im Firmennamen "
        "klares Indiz für Vermögens-Strukturierung. Anschluss: „Sie haben "
        "gerade eine Holding-/Beteiligungsstruktur aufgesetzt — typischer "
        "Anlass, neue Direktbeteiligungs-Optionen zu prüfen."
    ),
    BekanntmachungType.CAPITAL_INCREASE: (
        "Kapitalerhöhung (HRB {hrb}) — frisches Eigenkapital im Unternehmen, "
        "häufig vor strategischen Investitionen oder Diversifikation. "
        "Anschluss: „Diversifikation außerhalb des Kerngeschäfts steht "
        "üblicherweise als Nächstes."
    ),
    BekanntmachungType.OTHER: (
        "Bekanntmachung im HRB {hrb} — Trigger-Kontext im Gespräch klären."
    ),
}


def generate_hook(
    *,
    trigger_type: BekanntmachungType,
    hrb: str | None,
    person: PersonInfo,
    company_name: str,
) -> str:
    template = HOOK_TEMPLATES.get(trigger_type, HOOK_TEMPLATES[BekanntmachungType.OTHER])
    hrb_display = (hrb or "—").removeprefix("HRB ").removeprefix("HRB-")
    return template.format(hrb=hrb_display)


# ───────────────────────────────────────────────────────────────────────────
# Standard-Einwand-Antworten (Stichworte, Closer hat Fachwissen)
# ───────────────────────────────────────────────────────────────────────────


STANDARD_OBJECTIONS: list[dict[str, str]] = [
    {
        "objection": "Woher haben Sie meine Nummer?",
        "response": "Handelsregister-Eintrag öffentlich, Telefon via Firmen-Impressum.",
    },
    {
        "objection": "Helium klingt nach NASCO-Geschichte.",
        "response": "Star Oil Production Hamburg, ORRI direkt, keine Aktien-Konstruktion, keine Börsen-Versprechen.",
    },
    {
        "objection": "USA-Steuer ist mir zu komplex.",
        "response": "DBA US-DE, §15 EStG, Quellensteuer-Anrechnung — abgedeckt.",
    },
]


# ───────────────────────────────────────────────────────────────────────────
# Trigger-Summary (Datum + Was)
# ───────────────────────────────────────────────────────────────────────────


def trigger_summary(b: BekanntmachungRaw) -> str:
    parts = [
        b.bekanntmachung_date.strftime("%Y-%m-%d"),
    ]
    type_labels = {
        BekanntmachungType.SHAREHOLDER_CHANGE: "Anteilseignerwechsel",
        BekanntmachungType.GF_CHANGE: "Geschäftsführerwechsel",
        BekanntmachungType.NEW_REGISTRATION: "Neueintragung",
        BekanntmachungType.CAPITAL_INCREASE: "Kapitalerhöhung",
        BekanntmachungType.OTHER: "Bekanntmachung",
    }
    label = type_labels.get(b.bekanntmachung_type, "Bekanntmachung")
    hrb_display = (b.hrb_nummer or "—").removeprefix("HRB ").removeprefix("HRB-")
    parts.append(f"{label} im HRB {hrb_display}")
    if b.register_court:
        parts.append(f"({b.register_court})")
    return " — ".join(parts)


# ───────────────────────────────────────────────────────────────────────────
# Lead-ID-Generator (kurz, sprechend)
# ───────────────────────────────────────────────────────────────────────────


def lead_short_id(*, today: date, sequence: int) -> str:
    """z.B. DE-2026-W22-003"""
    iso_year, iso_week, _ = today.isocalendar()
    return f"DE-{iso_year}-W{iso_week:02d}-{sequence:03d}"


# ───────────────────────────────────────────────────────────────────────────
# MAIN: Dossier-Markdown bauen
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DossierInput:
    bekanntmachung: BekanntmachungRaw
    person: PersonInfo
    enrichment: CompanyEnrichment | None
    score: ScoreBreakdown
    phone: str | None
    phone_source: str | None
    short_id: str
    today: date


def render_dossier(d: DossierInput) -> str:
    b = d.bekanntmachung
    p = d.person
    e = d.enrichment

    # KEIN automatisches "Herr/Frau" — Vorname-→-Geschlecht-Heuristik unzuverlässig,
    # Closer macht das selbst beim Anruf.
    full_name = " ".join(filter(None, [p.first_name, p.last_name]))
    person_line = full_name.strip() or "—"

    role_line = f"{p.role} | {b.company_name}" if p.role else b.company_name
    location = ", ".join(filter(None, [b.company_postal_code, b.company_city]))
    if location:
        role_line = f"{role_line}, {location}"

    phone_str = d.phone or "_(Telefon offen — siehe Belege)_"
    phone_source = f" (Quelle: {d.phone_source})" if d.phone_source and d.phone else ""

    # Vermögens-Hint im Trigger-Block, wenn Enrichment da
    ek_hint = ""
    if e and e.equity_eur:
        ek_eur = f"€{e.equity_eur:,.0f}".replace(",", ".")
        year = f"JA {e.last_ja_year}" if e.last_ja_year else "JA"
        ek_hint = f"\n{year}: Eigenkapital {ek_eur}."

    freshness = (d.today - b.bekanntmachung_date).days

    hook = generate_hook(
        trigger_type=BekanntmachungType(b.bekanntmachung_type),
        hrb=b.hrb_nummer,
        person=p,
        company_name=b.company_name,
    )

    window = best_call_window(BekanntmachungType(b.bekanntmachung_type), p.role)

    # Einwände — gefiltert auf die Top 3 (Standard)
    objection_lines = []
    for i, o in enumerate(STANDARD_OBJECTIONS, start=1):
        objection_lines.append(f"{i}. \"{o['objection']}\" -> {o['response']}")
    objections = "\n".join(objection_lines)

    tier_label = (
        d.score.tier.upper() if isinstance(d.score.tier, str) else d.score.tier.value.upper()
    )
    md = f"""# LEAD {d.short_id} | Posterior {d.score.posterior:.2f} | Tier {tier_label}

**Person:** {person_line}
**Rolle:** {role_line}
**Telefon:** {phone_str}{phone_source}
**Beste Anrufzeit:** {window}

## Trigger (warum jetzt)
{trigger_summary(b)} — Trigger-Frische: {freshness} Tage.{ek_hint}

## Hook für Opener
{hook}

## Erwartete Einwände (Top 3, Stichworte)
{objections}

## Belege (Anhang)
- HR-Bekanntmachung: HRB {(b.hrb_nummer or "—").removeprefix("HRB ").removeprefix("HRB-")} ({b.register_court or "—"})
- Bekanntmachungs-Datum: {b.bekanntmachung_date.isoformat()}
"""
    if e and e.last_ja_year:
        md += f"- Bundesanzeiger JA {e.last_ja_year} (EK {e.equity_eur:,.0f} €)\n"

    return md
