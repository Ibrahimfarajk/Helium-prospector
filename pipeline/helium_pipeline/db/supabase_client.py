"""Supabase-Client für die Pipeline.

Nutzt service_role_key → bypasst RLS (Pipeline ist trusted Server-Komponente).
Web-Frontend nutzt anon_key + RLS-Policies.
"""

from __future__ import annotations

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

    # ─── Phase 8.2 — Read-Side für Rescore-CLI ─────────────────────────

    def fetch_active_leads(
        self, *, min_tier: str = "t2", limit: int = 30
    ) -> list[dict]:
        """Holt aktive Leads (nicht deleted, nicht do_not_contact) für Rescore."""
        tier_order = {"t1": 0, "t2": 1, "t3": 2}
        max_idx = tier_order.get(min_tier, 1)
        wanted = [t for t, i in tier_order.items() if i <= max_idx]
        try:
            r = (
                self.client.table("leads")
                .select(
                    "id,bekanntmachung_id,company_id,trigger_type,trigger_date,"
                    "person_first_name,person_last_name,person_role,phone,phone_source,"
                    "email,contact_channels,posterior_score,tier,is_gold,score_breakdown,"
                    "do_not_contact,deleted_at"
                )
                .in_("tier", wanted)
                .is_("deleted_at", None)
                .eq("do_not_contact", False)
                .order("posterior_score", desc=True)
                .limit(limit)
                .execute()
            )
            return r.data or []
        except Exception as e:
            log.warning("fetch_active_leads_failed", error=str(e))
            return []

    def fetch_bekanntmachung(self, bek_id: str) -> dict | None:
        try:
            r = (
                self.client.table("bekanntmachungen_raw")
                .select("*")
                .eq("id", bek_id)
                .single()
                .execute()
            )
            return r.data
        except Exception as e:
            log.debug("fetch_bek_failed", bek_id=bek_id, error=str(e))
            return None

    def fetch_company_bekanntmachungen(
        self, *, hrb_nummer: str | None, company_name: str, days_back: int = 90
    ) -> list[dict]:
        """Hol alle Bekanntmachungen einer Firma im N-Tage-Fenster für Momentum."""
        from datetime import date, timedelta

        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        try:
            q = (
                self.client.table("bekanntmachungen_raw")
                .select("hrb_nummer,company_name,bekanntmachung_date")
                .gte("bekanntmachung_date", cutoff)
            )
            if hrb_nummer:
                q = q.eq("hrb_nummer", hrb_nummer)
            else:
                q = q.eq("company_name", company_name)
            r = q.execute()
            return r.data or []
        except Exception as e:
            log.warning("fetch_company_beks_failed", error=str(e))
            return []

    def update_lead_score(
        self,
        lead_id: str,
        *,
        posterior_score: float,
        tier: str,
        is_gold: bool,
        gold_reason: str | None,
        score_breakdown: dict,
    ) -> bool:
        try:
            self.client.table("leads").update(
                _supabase_jsonable(
                    {
                        "posterior_score": posterior_score,
                        "tier": tier,
                        "is_gold": is_gold,
                        "gold_reason": gold_reason,
                        "score_breakdown": score_breakdown,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
            ).eq("id", lead_id).execute()
            return True
        except Exception as e:
            log.warning("update_lead_score_failed", lead_id=lead_id, error=str(e))
            return False

    # ─── Phase 8.2-P2 — Drift-Snapshots ────────────────────────────────

    def insert_drift_snapshot(self, snap_row: dict) -> bool:
        try:
            self.client.table("drift_snapshots").insert(
                _supabase_jsonable(snap_row)
            ).execute()
            return True
        except Exception as e:
            log.warning("drift_snapshot_insert_failed", error=str(e))
            return False

    def fetch_recent_drift_snapshots(self, *, limit: int = 7) -> list[dict]:
        try:
            r = (
                self.client.table("drift_snapshots")
                .select("posterior_mean,posterior_p95,n_kept,n_gold,timestamp")
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return r.data or []
        except Exception as e:
            log.warning("fetch_drift_snapshots_failed", error=str(e))
            return []
