"""Pydantic v2 Schemas — mirror the DB-Schema in shared/db_schema.sql.

Wir halten Python-Modelle und Postgres-Tabellen in Sync, indem die SQL-Definition
in shared/db_schema.sql die Source-of-Truth ist und dieses Modul deren Subset
für die Pipeline darstellt (Crawl→Score→Dossier→Insert).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ───────────────────────────────────────────────────────────────────────────
# ENUMS (must match db_schema.sql exactly)
# ───────────────────────────────────────────────────────────────────────────


class LeadTier(StrEnum):
    T1 = "t1"
    T2 = "t2"
    T3 = "t3"


class LeadStatus(StrEnum):
    NEW = "new"
    REVIEWING = "reviewing"
    CONTACTED = "contacted"
    IN_CONVERSATION = "in_conversation"
    MEETING_SET = "meeting_set"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    DO_NOT_CONTACT = "do_not_contact"


class BekanntmachungType(StrEnum):
    GF_CHANGE = "gf_change"
    SHAREHOLDER_CHANGE = "shareholder_change"
    NEW_REGISTRATION = "new_registration"
    CAPITAL_INCREASE = "capital_increase"
    OTHER = "other"


class CountryCode(StrEnum):
    DE = "DE"
    AT = "AT"
    CH = "CH"


# ───────────────────────────────────────────────────────────────────────────
# CORE MODELS
# ───────────────────────────────────────────────────────────────────────────


class BekanntmachungRaw(BaseModel):
    """Roh-Crawl-Eintrag, 1:1 zu bekanntmachungen_raw."""

    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    source: str  # 'handelsregister.de' / 'bundesanzeiger.de'
    bekanntmachung_type: BekanntmachungType
    hrb_nummer: str | None = None
    register_court: str | None = None
    company_name: str
    company_legal_form: str | None = None
    company_address: str | None = None
    company_postal_code: str | None = None
    company_city: str | None = None
    country_code: CountryCode = CountryCode.DE
    bekanntmachung_date: date
    raw_html: str | None = None
    raw_text: str | None = None
    parsed_payload: dict[str, Any] = Field(default_factory=dict)
    crawl_run_id: UUID
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CompanyEnrichment(BaseModel):
    """Optionale Bundesanzeiger-Anreicherung."""

    hrb_nummer: str
    register_court: str | None = None
    last_ja_year: int | None = None
    equity_eur: float | None = None
    balance_sum_eur: float | None = None
    website: str | None = None
    phone: str | None = None
    impressum_url: str | None = None
    # derived soft signals
    has_holding_in_name: bool = False
    has_vermoegen_in_name: bool = False
    has_family_office_hint: bool = False
    has_us_business_hint: bool = False
    # Phase-6.5-F1: BA-Cashflow-Indikator
    liquid_assets_eur: float | None = None  # Kassenbestand + Bankguthaben
    operating_cashflow_eur: float | None = None  # Cashflow lfd. Geschäftstätigkeit
    profit_eur: float | None = None  # Jahresüberschuss / Bilanzgewinn
    has_paragraph_match: bool = False  # §16/§34/§7g/§6b/§15a EStG im JA
    paragraph_matches: list[str] = Field(default_factory=list)  # gefundene §-Paragrafen
    # Phase-6.5-F2: Konzern-Cross-Ref
    wphg_voting_rights_count: int | None = None  # Anzahl Stimmrechts-Beteiligungen >=3%
    wphg_companies: list[str] = Field(default_factory=list)  # Firmennamen der Beteiligungen


class ContactChannel(BaseModel):
    """Ein einzelner Kontakt-Kanal mit Confidence (Phase 6.5)."""

    channel: str  # 'phone' | 'mobile' | 'email' | 'linkedin' | 'xing' | 'website'
    value: str
    source: str  # 'firmen-impressum:domain.de/impressum' | 'hr-eintrag' | 'manual' | 'persondossier'
    confidence: float = 0.5  # 0..1 — 1 = sicher, 0 = nur Vermutung
    notes: str | None = None


class PersonInfo(BaseModel):
    """Person aus einer Bekanntmachung (GF, Anteilseigner, etc.)."""

    first_name: str | None = None
    last_name: str
    role: str | None = None
    appointed_at: date | None = None


class ScoreBreakdown(BaseModel):
    """Bayes-Rechnung pro Lead — vollständig nachvollziehbar."""

    prior: float = 0.001
    likelihood_ratios: dict[str, float] = Field(default_factory=dict)
    """Map name → LR-value, e.g. {'trigger_§16_§34': 40, 'holding_struktur': 15}."""
    posterior: float
    tier: LeadTier
    hard_gates_passed: bool = True
    hard_gates_failed_reasons: list[str] = Field(default_factory=list)
    is_gold: bool = False
    gold_reason: str | None = None
    # Phase 8.2 — Cluster-Cap-Aufschlüsselung pro Signal-Familie
    family_breakdown: dict[str, dict] = Field(default_factory=dict)
    """{family: {lrs, strongest_key, dimmed_keys, log_odds_contribution}}."""


class Lead(BaseModel):
    """Kuratierter Lead — landet in leads-Tabelle."""

    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    bekanntmachung_id: UUID | None = None
    company_id: UUID | None = None

    # Person
    person_first_name: str | None = None
    person_last_name: str
    person_role: str | None = None
    person_appointed_at: date | None = None

    # Kontakt — legacy single-Value (für Backwards-Compat in DB+UI)
    phone: str | None = None
    phone_source: str | None = None
    email: str | None = None
    # Phase 6.5: Multi-Channel-Array, sortiert by confidence DESC
    contact_channels: list[ContactChannel] = Field(default_factory=list)

    # Trigger
    trigger_type: BekanntmachungType
    trigger_date: date
    trigger_summary: str

    # Scoring
    posterior_score: float
    tier: LeadTier
    score_breakdown: dict[str, Any]  # serialized ScoreBreakdown

    # Dossier
    dossier_markdown: str
    hook_text: str
    objection_handles: list[dict[str, str]] = Field(default_factory=list)

    # Workflow
    status: LeadStatus = LeadStatus.NEW
    best_call_window: str | None = None

    # Lifecycle
    do_not_contact: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawlRun(BaseModel):
    """Pipeline-Telemetrie — frühe Detektion der Pre-Mortem-Risiken."""

    id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: str = "running"  # running | success | failed | captcha
    pages_fetched: int = 0
    captchas_hit: int = 0
    bekanntmachungen_found: int = 0
    leads_created: int = 0
    error_message: str | None = None
    notes: str | None = None
