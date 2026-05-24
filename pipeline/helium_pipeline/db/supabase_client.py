"""Supabase-Client für die Pipeline.

Nutzt service_role_key → bypasst RLS (Pipeline ist trusted Server-Komponente).
Web-Frontend nutzt anon_key + RLS-Policies.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import structlog
from supabase import Client, create_client

from ..models import BekanntmachungRaw, CrawlRun, Lead
from ..settings import settings

log = structlog.get_logger()


def _supabase_jsonable(obj: Any) -> Any:
    """Konvertiere Pydantic/datetime/UUID zu JSON-serializable für supabase-py."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _supabase_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_supabase_jsonable(v) for v in obj]
    return obj


class SupabaseRepo:
    """Schreib-Layer für Crawl-Pipeline. Nutzt service_role_key."""

    def __init__(self, *, url: str | None = None, key: str | None = None):
        url = url or settings.SUPABASE_URL
        key = key or settings.SUPABASE_SERVICE_ROLE_KEY
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY müssen in .env sein "
                "(oder mock-mode in main.py via --dry-run nutzen)."
            )
        self.client: Client = create_client(url, key)

    # ─── Crawl-Runs ─────────────────────────────────────────────────────

    def insert_crawl_run(self, run: CrawlRun) -> None:
        self.client.table("crawl_runs").insert(
            _supabase_jsonable(run.model_dump())
        ).execute()

    def update_crawl_run(self, run_id: UUID, patch: dict[str, Any]) -> None:
        self.client.table("crawl_runs").update(_supabase_jsonable(patch)).eq(
            "id", str(run_id)
        ).execute()

    # ─── Bekanntmachungen ──────────────────────────────────────────────

    def upsert_bekanntmachung(self, bek: BekanntmachungRaw) -> bool:
        """Upsert via unique (hrb_nummer, bekanntmachung_date, bekanntmachung_type).

        Returns True wenn neu inserted, False wenn schon existiert.
        """
        payload = _supabase_jsonable(bek.model_dump())
        try:
            self.client.table("bekanntmachungen_raw").upsert(
                payload,
                on_conflict="hrb_nummer,bekanntmachung_date,bekanntmachung_type",
                ignore_duplicates=True,
            ).execute()
            return True
        except Exception as e:
            log.warning("bek_upsert_failed", error=str(e), hrb=bek.hrb_nummer)
            return False

    # ─── Leads ──────────────────────────────────────────────────────────

    def insert_lead(self, lead: Lead) -> bool:
        payload = _supabase_jsonable(lead.model_dump())
        try:
            self.client.table("leads").insert(payload).execute()
            return True
        except Exception as e:
            log.warning("lead_insert_failed", error=str(e))
            return False
