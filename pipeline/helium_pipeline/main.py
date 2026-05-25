"""CLI-Entry: helium-pipeline run [--dry-run] [--max-pages N]

Orchestriert: Crawl → Bundesanzeiger-Enrich → Score → Dossier → DB.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

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
    max_leads: int | None = None,  # Hard-Cap auf yielded items (Live-Tests)
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
    # Phase 8.2-B5: scored_leads für Drift-Monitoring sammeln
    scored_leads_for_drift: list[dict] = []

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
                    if max_leads is not None and summary["bekanntmachungen"] >= max_leads:
                        log.info("max_leads_cap_reached", cap=max_leads)
                        break
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

                    # Drift-Monitor: jeden gescorten Lead sammeln
                    scored_leads_for_drift.append({
                        "lead_id": str(bek.id),
                        "posterior": float(breakdown.posterior),
                        "tier": breakdown.tier.value if hasattr(breakdown.tier, "value") else str(breakdown.tier),
                        "is_gold": bool(breakdown.is_gold),
                        "gold_reason": breakdown.gold_reason,
                        "hard_gates_passed": bool(breakdown.hard_gates_passed),
                    })

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
                        trigger_summary=_format_trigger_summary(bek),
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

        # Drift-Monitor: Snapshot über alle scored Leads dieses Runs
        if scored_leads_for_drift:
            from .monitoring import compute_run_snapshot
            from .monitoring import record_run as record_drift
            snap = compute_run_snapshot(
                run_id=run.id,
                scored_leads=scored_leads_for_drift,
            )
            record_drift(snap, repo=repo if not dry_run else None)
            summary["drift_alert"] = snap.alert

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


_TRIGGER_LABELS = {
    "shareholder_change": "Anteilseignerwechsel",
    "gf_change": "Geschäftsführerwechsel",
    "new_registration": "Neueintragung",
    "capital_increase": "Kapitalerhöhung",
    "other": "Bekanntmachung",
}


def _format_trigger_summary(bek) -> str:
    """Schöner Trigger-Summary: `<Datum> — <Typ> im HRB <Nummer> — (<Gericht>)`"""
    label = _TRIGGER_LABELS.get(str(bek.bekanntmachung_type), "Bekanntmachung")
    hrb_clean = (bek.hrb_nummer or "—").removeprefix("HRB ").removeprefix("HRB-")
    parts = [
        bek.bekanntmachung_date.isoformat(),
        "—",
        f"{label} im HRB {hrb_clean}",
    ]
    if bek.register_court:
        parts.append(f"— ({bek.register_court})")
    return " ".join(parts)


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
    "--max-leads",
    type=int,
    default=None,
    help="Hard-Cap auf Anzahl verarbeiteter Bekanntmachungen (Live-Test).",
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
    max_leads: int | None,
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
            max_leads=max_leads,
        )
    )


# ───────────────────────────────────────────────────────────────────────────
# Phase 8.2-P1: rescore-CLI für Delta-Cron-Runs (09/13 UTC)
# ───────────────────────────────────────────────────────────────────────────


def _reconstruct_enrichment_from_lrs(
    *, hrb_nummer: str, old_lrs: dict, today_year: int
):
    """Rück-Rekonstruktion eines CompanyEnrichment aus alten LR-Keys.

    Wir nutzen die LR-Keys als Indikator welche Schwellen erreicht waren
    und setzen Werte am UNTEREN Rand der Schwelle (konservativ). So bleibt
    der Re-Score konsistent mit der ursprünglichen Score-Entscheidung.

    Achtung: das ist VERMUTLICH genau genug für Tier-Stabilität, nicht für
    LR-Wert-Veränderungen wenn die Schwellen sich ändern.
    """
    from .models import CompanyEnrichment

    enr = CompanyEnrichment(hrb_nummer=hrb_nummer or "RESCORE")

    # EK
    if "ek_ge_10m" in old_lrs:
        enr.equity_eur = 10_000_000.0
    elif "ek_ge_2m" in old_lrs:
        enr.equity_eur = 2_000_000.0
    elif "ek_ge_500k" in old_lrs:
        enr.equity_eur = 500_000.0

    # Liquide Mittel
    if "liquid_assets_ge_5m" in old_lrs:
        enr.liquid_assets_eur = 5_000_000.0
    elif "liquid_assets_ge_1m" in old_lrs:
        enr.liquid_assets_eur = 1_000_000.0
    elif "liquid_assets_ge_500k" in old_lrs:
        enr.liquid_assets_eur = 500_000.0

    # Operating Cashflow
    if "operating_cashflow_ge_1m" in old_lrs:
        enr.operating_cashflow_eur = 1_000_000.0
    elif "operating_cashflow_ge_500k" in old_lrs:
        enr.operating_cashflow_eur = 500_000.0
    elif "operating_cashflow_ge_200k" in old_lrs:
        enr.operating_cashflow_eur = 200_000.0
    elif "cashflow_negative" in old_lrs:
        enr.operating_cashflow_eur = -1.0  # any negative

    # Profit
    if "profit_ge_1m" in old_lrs:
        enr.profit_eur = 1_000_000.0
    elif "profit_ge_500k" in old_lrs:
        enr.profit_eur = 500_000.0
    elif "profit_ge_200k" in old_lrs:
        enr.profit_eur = 200_000.0

    # Paragraph + WpHG
    enr.has_paragraph_match = "tax_paragraph_match_ja" in old_lrs
    if "wphg_voting_rights_5plus" in old_lrs:
        enr.wphg_voting_rights_count = 5
    elif "wphg_voting_rights_3plus" in old_lrs:
        enr.wphg_voting_rights_count = 3

    # Name-Hints (für Affinity-Rekonstruktion sind die schon im name selber)
    enr.has_family_office_hint = "name_family_office" in old_lrs
    enr.has_us_business_hint = "us_business_hint" in old_lrs

    # last_ja_year — wenn liquidity_data_stale-Flag NICHT gesetzt war, ist JA frisch.
    # Setze auf today_year falls Liquiditäts-Daten da sind und kein stale-Flag.
    if "liquidity_data_stale" in old_lrs:
        enr.last_ja_year = today_year - 3  # absichtlich alt
    elif enr.liquid_assets_eur or enr.operating_cashflow_eur or enr.profit_eur:
        enr.last_ja_year = today_year - 1  # frisch

    return enr


def _rescore_pipeline(*, limit: int, min_tier: str, dry_run: bool) -> dict:
    """Hol aktive Leads, re-score mit aktuellen Filtern + Drift-Monitor."""
    from datetime import date as date_cls

    from .models import (
        BekanntmachungRaw as BekRaw,
    )
    from .models import (
        BekanntmachungType,
        CountryCode,
        CrawlRun,
    )
    from .monitoring import compute_run_snapshot, record_run
    from .scoring.bayes import ScoringInput, score

    configure_logging()
    run = CrawlRun(notes="rescore-only (delta-mode)")
    log.info("rescore_start", run_id=str(run.id), limit=limit, min_tier=min_tier)

    repo = SupabaseRepo()
    repo.insert_crawl_run(run)

    leads = repo.fetch_active_leads(min_tier=min_tier, limit=limit)
    summary: dict[str, Any] = {
        "run_id": str(run.id),
        "mode": "rescore",
        "fetched": len(leads),
        "rescored": 0,
        "tier_changes": [],
        "scored_leads": [],
    }

    for lead in leads:
        bek_id = lead.get("bekanntmachung_id")
        if not bek_id:
            continue
        bek_row = repo.fetch_bekanntmachung(bek_id)
        if not bek_row:
            continue

        # Rekonstruiere BekanntmachungRaw + Enrichment aus DB
        try:
            bek = BekRaw(
                id=bek_row["id"],
                source=bek_row.get("source", "rescore"),
                bekanntmachung_type=BekanntmachungType(bek_row["bekanntmachung_type"]),
                hrb_nummer=bek_row.get("hrb_nummer"),
                register_court=bek_row.get("register_court"),
                company_name=bek_row["company_name"],
                company_legal_form=bek_row.get("company_legal_form"),
                company_address=bek_row.get("company_address"),
                company_postal_code=bek_row.get("company_postal_code"),
                company_city=bek_row.get("company_city"),
                country_code=CountryCode(bek_row.get("country_code", "DE")),
                bekanntmachung_date=date_cls.fromisoformat(bek_row["bekanntmachung_date"]),
                raw_html=bek_row.get("raw_html"),
                raw_text=bek_row.get("raw_text"),
                parsed_payload=bek_row.get("parsed_payload") or {},
                crawl_run_id=bek_row.get("crawl_run_id") or run.id,
            )
        except Exception as e:
            log.warning("rescore_bek_parse_failed", bek_id=bek_id, error=str(e))
            continue

        # Enrichment aus altem score_breakdown rück-rekonstruieren.
        # Wir nutzen die LR-Keys als Indikator welche Schwellen erreicht waren
        # und setzen Werte am UNTEREN Rand der Schwelle (konservativ).
        # Das hält Re-Score-Konsistenz mit der ursprünglichen Score-Entscheidung.
        old_breakdown = lead.get("score_breakdown") or {}
        old_lrs = old_breakdown.get("likelihood_ratios") or {}
        enrichment = _reconstruct_enrichment_from_lrs(
            hrb_nummer=bek.hrb_nummer or "RESCORE",
            old_lrs=old_lrs,
            today_year=date_cls.today().year,
        )

        # Momentum: hol previous Bekanntmachungen aus DB
        previous_beks = repo.fetch_company_bekanntmachungen(
            hrb_nummer=bek.hrb_nummer,
            company_name=bek.company_name,
            days_back=90,
        )

        # Re-Score
        new_breakdown = score(ScoringInput(
            bekanntmachung=bek,
            enrichment=enrichment,
            contact_channels=lead.get("contact_channels") or None,
            previous_bekanntmachungen=previous_beks,
            person_first_name=lead.get("person_first_name"),
            person_last_name=lead.get("person_last_name"),
        ))

        old_tier = lead.get("tier")
        new_tier = new_breakdown.tier if isinstance(new_breakdown.tier, str) else new_breakdown.tier.value
        if old_tier != new_tier:
            summary["tier_changes"].append({
                "lead_id": lead["id"],
                "old_tier": old_tier,
                "new_tier": new_tier,
                "old_post": lead.get("posterior_score"),
                "new_post": round(new_breakdown.posterior, 4),
            })

        if not dry_run:
            repo.update_lead_score(
                lead["id"],
                posterior_score=new_breakdown.posterior,
                tier=new_tier,
                is_gold=new_breakdown.is_gold,
                gold_reason=new_breakdown.gold_reason,
                score_breakdown=new_breakdown.model_dump(),
            )
        summary["rescored"] += 1
        summary["scored_leads"].append({
            "lead_id": lead["id"],
            "posterior": new_breakdown.posterior,
            "tier": new_tier,
            "is_gold": new_breakdown.is_gold,
            "gold_reason": new_breakdown.gold_reason,
            "hard_gates_passed": new_breakdown.hard_gates_passed,
        })

    # Drift-Monitor: snapshot über die rescored Leads
    snap = compute_run_snapshot(
        run_id=run.id,
        scored_leads=summary["scored_leads"],
    )
    record_run(snap, repo=repo)
    summary["drift_alert"] = snap.alert

    # Finalize crawl_run
    run.finished_at = datetime.now(UTC)
    run.status = "success"
    run.leads_created = 0  # rescore creates none
    run.notes = f"rescore: {summary['rescored']}/{summary['fetched']} leads, {len(summary['tier_changes'])} tier changes"
    repo.update_crawl_run(
        run.id,
        {
            "finished_at": run.finished_at,
            "status": run.status,
            "leads_created": run.leads_created,
            "notes": run.notes,
        },
    )

    log.info("rescore_done", **{k: v for k, v in summary.items() if k != "scored_leads"})
    return summary


@cli.command("rescore")
@click.option("--limit", default=30, show_default=True, help="Max Leads zum Re-Scoren")
@click.option(
    "--min-tier",
    type=click.Choice(["t1", "t2", "t3"]),
    default="t2",
    show_default=True,
    help="Nur Leads ab diesem Tier",
)
@click.option("--dry-run", is_flag=True, help="Kein DB-Write")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("./local_data"),
    show_default=True,
)
def rescore_cmd(limit: int, min_tier: str, dry_run: bool, output_dir: Path):
    """Re-score active leads with current filters + drift-monitor.

    Use-case: Delta-Cron-Runs (09/13 UTC) ohne HR-Crawl.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = _rescore_pipeline(limit=limit, min_tier=min_tier, dry_run=dry_run)
    summary_file = output_dir / f"rescore_summary_{summary['run_id']}.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    log.info("rescore_summary_written", path=str(summary_file))


if __name__ == "__main__":
    cli()
