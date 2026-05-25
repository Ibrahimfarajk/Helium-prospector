"""Schema-Import: shared/db_schema.sql → Supabase Postgres.

Nutzt direkten psycopg-Connect zum Supabase-Pooler (eu-central-1).
Liest .env aus pipeline/.env + DATABASE_PASSWORD aus Argv/Env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

# ─── Settings ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_FILE = ROOT / "shared" / "db_schema.sql"

# Supabase Direct-Connection (eu-central-1 Frankfurt)
# Format: postgresql://postgres.[project-ref]:[password]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
# (session-mode-pooler: Port 5432; transaction-mode: Port 6543)
PROJECT_REF = "jkqgpfbnplthchifwhqy"


def build_connstr() -> str:
    pw = os.environ.get("DATABASE_PASSWORD")
    if not pw:
        print("ERROR: DATABASE_PASSWORD env var not set", file=sys.stderr)
        sys.exit(1)

    mode = os.environ.get("CONN_MODE", "session_pooler")
    if mode == "direct":
        # Direct-Connect (benötigt IPv6 ggf.)
        return f"postgresql://postgres:{pw}@db.{PROJECT_REF}.supabase.co:5432/postgres"
    if mode == "transaction_pooler":
        return (
            f"postgresql://postgres.{PROJECT_REF}:{pw}@"
            f"aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        )
    # default: session_pooler (port 5432)
    return (
        f"postgresql://postgres.{PROJECT_REF}:{pw}@"
        f"aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    )


def main() -> int:
    if not SCHEMA_FILE.exists():
        print(f"ERROR: {SCHEMA_FILE} not found", file=sys.stderr)
        return 1

    sql_text = SCHEMA_FILE.read_text(encoding="utf-8")
    print(f"Loaded {len(sql_text)} bytes from {SCHEMA_FILE}")
    print("Connecting to Supabase (eu-central-1)...")

    try:
        with psycopg.connect(build_connstr(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
            print("OK schema imported")

            # Verify: count tables
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select table_name from information_schema.tables
                    where table_schema = 'public'
                    order by table_name;
                    """
                )
                tables = [r[0] for r in cur.fetchall()]
                print(f"\nTables in public schema ({len(tables)}):")
                for t in tables:
                    print(f"  - {t}")
        return 0
    except psycopg.errors.DuplicateObject as e:
        print(f"WARN duplicate object — schema already imported? {e}", file=sys.stderr)
        return 0
    except psycopg.Error as e:
        print(f"ERROR psycopg: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
