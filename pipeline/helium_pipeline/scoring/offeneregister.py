"""OffeneRegister-Bulk-Baseline-Lookup (Phase 6.5 F5).

Nutzt das 3.5 GB SQLite-Snapshot (Stand 2022-10-21) von OffeneRegister.de.

Zwei Lookup-Funktionen:
1. is_company_established_before(name, year=2019) — existiert die Firma vor cutoff?
   → "etabliert" = kein Jung-GmbH-Risiko
2. is_mailbox_cluster_address(address) — Match gegen extrahierte 300 Briefkasten-Cluster
   → ergänzt anti_filters.address_contains_mailbox_provider

Performance:
- Initial-Open: ~50 ms (FTS5-Index)
- Per-Lookup: 5-30 ms (FTS5 + COUNT-Aggregation)
- Module nutzt Cached-Connection (thread-local would be cleaner; pipeline ist single-process)
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import structlog

log = structlog.get_logger()


# ───────────────────────────────────────────────────────────────────────────
# Paths
# ───────────────────────────────────────────────────────────────────────────

_DB_PATH = Path.home() / ".helium-pipeline" / "offeneregister" / "handelsregister.db"
_MAILBOX_JSON = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "shared"
    / "mailbox_clusters.json"
)


# ───────────────────────────────────────────────────────────────────────────
# Connection — lazy, single-process cached
# ───────────────────────────────────────────────────────────────────────────

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection | None:
    """Lazy-open SQLite. Return None wenn DB nicht da."""
    global _conn
    if _conn is not None:
        return _conn
    if not _DB_PATH.exists():
        log.warning("offeneregister_db_missing", path=str(_DB_PATH))
        return None
    try:
        _conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True, timeout=10.0)
        _conn.execute("PRAGMA query_only = ON")
        log.info("offeneregister_db_opened", size_mb=_DB_PATH.stat().st_size // (1024 * 1024))
    except Exception as e:
        log.warning("offeneregister_db_open_failed", error=str(e))
        return None
    return _conn


# ───────────────────────────────────────────────────────────────────────────
# Mailbox-Cluster (loaded from JSON)
# ───────────────────────────────────────────────────────────────────────────

_mailbox_cache: dict | None = None
# Phase-7-Box-4: Pre-compute cluster cores → 126× speedup
_cluster_cores_cache: list[tuple[set[str], int | None]] | None = None


def _load_mailbox_clusters() -> dict:
    global _mailbox_cache, _cluster_cores_cache
    if _mailbox_cache is not None:
        return _mailbox_cache
    try:
        _mailbox_cache = json.loads(_MAILBOX_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("mailbox_clusters_load_failed", error=str(e))
        _mailbox_cache = {"clusters": []}
    # Pre-compute cluster cores ONCE — eviction would invalidate this too
    _cluster_cores_cache = [
        (_extract_address_cores(c["address_pattern"]), c.get("gmbh_count"))
        for c in _mailbox_cache.get("clusters", [])
    ]
    return _mailbox_cache


def _normalize_address(s: str) -> str:
    s = s.lower()
    # Replacement-Char (OffeneRegister-mojibake) → leeren string
    s = s.replace("�", "")
    # Umlaute → ASCII-equivalent
    for src, dst in [("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")]:
        s = s.replace(src, dst)
    # "Strasse|Strase|Strae|Straße|Str." als Suffix bei einem Wort → "str"
    # Greift auch "Friedrichstrae" (mojibake), "Hauptstrasse" (Schweiz), etc.
    s = re.sub(r"(?:strasse|strase|strae|straße)\b", "str", s)
    s = re.sub(r"\bstr\.?\b", "str", s)
    s = re.sub(r"[.,;]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Extract "street + number" core from a cluster-pattern
_STREET_CORE = re.compile(
    r"\b([a-z][\w-]*(?:str|straße|allee|platz|gasse|weg|ring|hof|markt|ufer|h[öo]he|hoehe))\s*(\d+[a-z]?(?:[-/]\d+[a-z]?)?)",
    re.IGNORECASE,
)


def _extract_address_cores(s: str) -> set[str]:
    """Extrahiere kanonisierte 'street + number' Tokens aus einer Adresse."""
    norm = _normalize_address(s)
    cores: set[str] = set()
    for m in _STREET_CORE.finditer(norm):
        street = m.group(1).replace("straße", "str").replace("strae", "str")
        number = m.group(2).strip()
        cores.add(f"{street} {number}")
    return cores


def is_mailbox_cluster_address(address: str | None) -> tuple[bool, int | None]:
    """True wenn Adresse Street+Number-Core-Match auf einen >100-Cluster.
    Returns (is_match, gmbh_count if match)."""
    if not address:
        return (False, None)
    input_cores = _extract_address_cores(address)
    if not input_cores:
        return (False, None)
    _load_mailbox_clusters()  # ensures _cluster_cores_cache is populated
    assert _cluster_cores_cache is not None
    for cluster_cores, gmbh_count in _cluster_cores_cache:
        if cluster_cores & input_cores:  # Schnittmenge
            return (True, gmbh_count)
    return (False, None)


# ───────────────────────────────────────────────────────────────────────────
# Established-Check via SQLite
# ───────────────────────────────────────────────────────────────────────────


def is_company_established_before(
    *,
    company_name: str,
    year: int = 2019,
) -> tuple[bool, str | None]:
    """True wenn Firma laut OffeneRegister vor `year` gegründet.

    Returns (is_established, founded_date_iso if match).

    Bei Missing-DB: graceful return (None, None) → kein Penalty.
    """
    conn = _get_conn()
    if conn is None:
        return (False, None)

    # FTS5-Match auf Firmennamen
    try:
        cur = conn.cursor()
        # FTS5 mag keine Sonderzeichen — escape via "
        safe = re.sub(r'[^\w\s]', " ", company_name).strip()
        if not safe or len(safe) < 4:
            return (False, None)

        cur.execute(
            """
            select c.foundedDate
            from NamesFts n
            join Companies c on c.companyId = n.companyId
            where n.name match ?
            and c.foundedDate is not null
            order by c.foundedDate asc
            limit 1
            """,
            (f'"{safe}"',),
        )
        row = cur.fetchone()
        if row and row[0]:
            founded = str(row[0])  # ISO date string
            try:
                founded_year = int(founded[:4])
                return (founded_year < year, founded)
            except (ValueError, IndexError):
                return (False, founded)
    except Exception as e:
        log.warning("offeneregister_lookup_failed", error=str(e), name=company_name[:50])

    return (False, None)
