"""CLI-Entry: helium-pipeline run [--dry-run] [--max-pages N]

Orchestriert: Crawl → Bundesanzeiger-Enrich → Score → Dossier → DB.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import click
import httpx
import structlog

from .crawlers.bundesanzeiger import fetch_company_enrichment
from .crawlers.handelsregister import (
    CaptchaDetected,
    crawl_bekanntmachungen,
)
from .crawlers.mock_source import generate_mock_bekanntmachungen
from .db.supabase_client import SupabaseRepo
from .dossier.generator import (
    DossierInput,
    best_call_window,
    generate_hook,
    lead_short_id,
    render_dossier,
)
from .logging_setup import configure_logging
from .models import (
    BekanntmachungType,
    CrawlRun,
    Lead,
    PersonInfo,
)
from .scoring.bayes import ScoringInput, score, should_keep
from .settings import settings
from .telephony.phone_finder import find_phone

log = structlog.get_logger()


async def run_pipeline(
    *,
    dry_run: bool,
    max_pages: int,
    days_back: int,
    output_dir: Path,
    source: str = "live",  # "live" oder "mock"
    mock_count: int = 25,
) -> None:
    configure_logging()
    run = CrawlRun()
    log.info("pipeline_start", run_id=str(run.id), dry_run=dry_run)

    repo: SupabaseRepo | None = None
    if not dry_run:
        repo = SupabaseRepo()
        repo.insert_crawl_run(run)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": str(run.id),
        "started_at": run.started_at.isoformat(),
        "dry_run": dry_run,
        "bekanntmachungen": 0,
        "leads_created": 0,
        "tiers": {"t1": 0, "t2": 0, "t3": 0, "dropped": 0},
        "sample_dossiers": [],
    }

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.PIPELINE_USER_AGENT},
            timeout=30.0,
        ) as http:
            seq = 0
            today = date.today()
            try:
                if source == "mock":
                    log.info("using_mock_source", count=mock_count)
                    iterator = _to_async_iter(
                        generate_mock_bekanntmachungen(
                            crawl_run_id=run.id, count=mock_count
                        )
                    )
                else:
                    iterator = crawl_bekanntmachungen(
                        crawl_run_id=run.id,
                        days_back=days_back,
                        max_pages=max_pages,
                    )
                async for bek in iterator:
                    summary["bekanntmachungen"] += 1

                    # 1. Bundesanzeiger-Enrich (nur bei klar trigger-relevanten Typen)
                    enrichment = None
                    if bek.hrb_nummer and bek.bekanntmachung_type in {
                        BekanntmachungType.SHAREHOLDER_CHANGE.value,
                        BekanntmachungType.NEW_REGISTRATION.value,
                        BekanntmachungType.CAPITAL_INCREASE.value,
                    }:
                        try:
                            enrichment = await fetch_company_enrichment(
                                hrb_nummer=bek.hrb_nummer,
                                company_name=bek.company_name,
                                client=http,
                            )
                        except Exception as e:
                            log.warning("enrichment_failed", error=str(e))

                    # 2. Score
                    breakdown = score(
                        ScoringInput(
                            bekanntmachung=bek,
                            enrichment=enrichment,
                            today=today,
                        )
                    )

                    if not should_keep(breakdown):
                        summary["tiers"]["dropped"] += 1
                        if not dry_run and repo:
                            repo.upsert_bekanntmachung(bek)  # immer raw speichern
                        continue

                    # 3. Person extrahieren (heuristisch aus parsed_payload oder raw_text)
                    person = _extract_person(bek)

                    # 4. Telefon-Suche
                    phone_result = await find_phone(
                        company_name=bek.company_name,
                        city=bek.company_city,
                        client=http,
                    )

                    # 5. Dossier rendern
                    seq += 1
                    short_id = lead_short_id(today=today, sequence=seq)
                    dossier_md = render_dossier(
                        DossierInput(
                            bekanntmachung=bek,
                            person=person,
                            enrichment=enrichment,
                            score=breakdown,
                            phone=phone_result.phone,
                            phone_source=phone_result.source,
                            short_id=short_id,
                            today=today,
                        )
                    )

                    # 6. Lead-Objekt
                    hook = generate_hook(
                        trigger_type=BekanntmachungType(bek.bekanntmachung_type),
                        hrb=bek.hrb_nummer,
                        person=person,
                        company_name=bek.company_name,
                    )
                    lead = Lead(
                        bekanntmachung_id=bek.id,
                        person_first_name=person.first_name,
                        person_last_name=person.last_name,
                        person_role=person.role,
                        person_appointed_at=person.appointed_at,
                        phone=phone_result.phone,
                        phone_source=phone_result.source,
                        trigger_type=BekanntmachungType(bek.bekanntmachung_type),
                        trigger_date=bek.bekanntmachung_date,
                        trigger_summary=f"{bek.bekanntmachung_type} HRB {bek.hrb_nummer or '—'}",
                        posterior_score=breakdown.posterior,
                        tier=breakdown.tier,
                        score_breakdown=breakdown.model_dump(),
                        dossier_markdown=dossier_md,
                        hook_text=hook,
                        best_call_window=best_call_window(
                            BekanntmachungType(bek.bekanntmachung_type), person.role
                        ),
                    )

                    summary["leads_created"] += 1
                    summary["tiers"][breakdown.tier.value if hasattr(breakdown.tier, 'value') else str(breakdown.tier)] += 1

                    # Sample-Dossiers für Review speichern
                    if len(summary["sample_dossiers"]) < 5:
                        dossier_file = output_dir / f"sample_{short_id}.md"
                        dossier_file.write_text(dossier_md, encoding="utf-8")
                        summary["sample_dossiers"].append(str(dossier_file))

                    if not dry_run and repo:
                        repo.upsert_bekanntmachung(bek)
                        repo.insert_lead(lead)

                    # DSGVO: nur Aggregate + HRB in Logs, kein Personen-Name / Telefon
                    log.info(
                        "lead_created",
                        short_id=short_id,
                        tier=str(breakdown.tier),
                        posterior=round(breakdown.posterior, 4),
                        hrb=bek.hrb_nummer,
                        court=bek.register_court,
                    )

            except CaptchaDetected as e:
                log.error("captcha_aborting", error=str(e))
                run.status = "captcha"
                run.error_message = str(e)
                summary["aborted_by_captcha"] = True

        # Finalize
        run.finished_at = datetime.now(UTC)
        run.status = run.status if run.status != "running" else "success"
        run.bekanntmachungen_found = summary["bekanntmachungen"]
        run.leads_created = summary["leads_created"]

        if not dry_run and repo:
            repo.update_crawl_run(
                run.id,
                {
                    "finished_at": run.finished_at,
                    "status": run.status,
                    "bekanntmachungen_found": run.bekanntmachungen_found,
                    "leads_created": run.leads_created,
                    "error_message": run.error_message,
                },
            )

    finally:
        summary_file = output_dir / f"run_summary_{run.id}.json"
        summary_file.write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        log.info(
            "pipeline_done",
            run_id=str(run.id),
            summary=summary,
            summary_file=str(summary_file),
        )


_STOPWORDS = {
    # Falsch-Positiv-Quellen — keine Vornamen/Nachnamen
    "Bestellt", "Bestellung", "Geschäftsführer", "Geschäftsführung",
    "Gesellschafter", "Vorstand", "Prokurist", "Liquidator",
    "Veränderung", "Verwaltung", "Vertretung", "Befugnis",
    "Übertragung", "Stammkapital", "Sitz", "Gegenstand", "Anteil",
    "Anteile", "Geschäftsanteile", "Beteiligungen", "Vermögens",
    "Person", "Unternehmen", "Gesellschaft", "Holding", "GmbH",
    "Kapital", "Erhöhung", "Neueintragung", "NewCo", "Co", "KG",
    "Eingetragen", "Niederlassung", "EUR",
}

# Anker: nach diesen Phrasen kommt der Person-Name in HR-Bekanntmachungen
_PERSON_ANCHORS = re.compile(
    r"(?:Bestellt(?:\s+als\s+Geschäftsführer)?|Geschäftsführer|"
    r"Gesellschafter|Vorstand|Übertragung\s+der\s+Geschäftsanteile\s+durch)"
    r"\s*:?\s*\n?",
    re.IGNORECASE,
)


def _extract_person(bek) -> PersonInfo:
    """Versuche Person aus raw_text zu extrahieren.

    Strategie: erst Anker-basiert nach "Bestellt:" / "Geschäftsführer:" suchen,
    dann ersten plausiblen Namen extrahieren.
    """
    text = bek.raw_text or ""

    # Cut off vor dem Anker → suche im Rest-Text
    anchor_match = _PERSON_ANCHORS.search(text)
    search_region = text[anchor_match.end():] if anchor_match else text

    # Pattern: "Nachname, Vorname" (dominantes HR-Format)
    for m in re.finditer(
        r"\b([A-ZÄÖÜ][a-zäöüß-]+),\s+([A-ZÄÖÜ][a-zäöüß-]+)\b",
        search_region,
    ):
        last = m.group(1)
        first = m.group(2)
        if last in _STOPWORDS or first in _STOPWORDS:
            continue
        return PersonInfo(
            first_name=first,
            last_name=last,
            role=_guess_role(text),
        )

    # Pattern: "Vorname Nachname" — fallback
    for m in re.finditer(
        r"\b([A-ZÄÖÜ][a-zäöüß-]+)\s+([A-ZÄÖÜ][a-zäöüß-]+(?:-[A-ZÄÖÜ][a-zäöüß-]+)?)\b",
        search_region,
    ):
        first = m.group(1)
        last = m.group(2)
        if first in _STOPWORDS or last in _STOPWORDS:
            continue
        return PersonInfo(
            first_name=first,
            last_name=last,
            role=_guess_role(text),
        )

    return PersonInfo(last_name="—", role=_guess_role(text))


def _guess_role(text: str) -> str | None:
    low = text.lower()
    if "geschäftsführer" in low or "geschaeftsfuehrer" in low:
        return "Geschäftsführer"
    if "gesellschafter" in low:
        return "Gesellschafter"
    if "vorstand" in low:
        return "Vorstand"
    return None


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """helium-pipeline — Lead-Generation CLI."""


async def _to_async_iter(items):
    for x in items:
        yield x


@cli.command("run")
@click.option("--dry-run", is_flag=True, help="Kein DB-Write; nur stdout + sample-files.")
@click.option("--max-pages", default=3, show_default=True, help="Sicherheits-Cap.")
@click.option("--days-back", default=1, show_default=True, help="Wieviele Tage rückwirkend.")
@click.option(
    "--source",
    type=click.Choice(["live", "mock"]),
    default="live",
    show_default=True,
    help="'live' = handelsregister.de, 'mock' = synthetische Test-Daten",
)
@click.option(
    "--mock-count",
    default=25,
    show_default=True,
    help="Anzahl Mock-Bekanntmachungen (nur bei --source=mock)",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("./local_data"),
    show_default=True,
)
def run_cmd(
    dry_run: bool,
    max_pages: int,
    days_back: int,
    source: str,
    mock_count: int,
    output_dir: Path,
):
    """Crawl handelsregister.de + score + (optional) push to Supabase."""
    asyncio.run(
        run_pipeline(
            dry_run=dry_run,
            max_pages=max_pages,
            days_back=days_back,
            output_dir=output_dir,
            source=source,
            mock_count=mock_count,
        )
    )


if __name__ == "__main__":
    cli()
