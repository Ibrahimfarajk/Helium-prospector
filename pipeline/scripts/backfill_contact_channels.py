"""Backfill: legacy phone/email → contact_channels JSONB-Array.

Lädt alle Leads mit contact_channels == [] und füllt sie aus den
legacy phone/email-Spalten. Confidence 0.7, source = "legacy_migration".

Idempotent: Leads die schon Channels haben, werden übersprungen.
"""

from __future__ import annotations

import os
import re
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client


def main() -> int:
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set", file=sys.stderr)
        return 1

    sb = create_client(url, key)
    r = sb.table("leads").select("id,phone,phone_source,email,contact_channels").execute()
    leads = r.data
    print(f"Total leads: {len(leads)}")

    updated = 0
    skipped = 0
    no_data = 0

    for lead in leads:
        existing = lead.get("contact_channels") or []
        if existing:
            skipped += 1
            continue

        channels = []
        phone = lead.get("phone")
        if phone:
            digits = re.sub(r"[^\d]", "", phone)
            is_mobile = bool(re.match(r"^(?:49)?01[567]", digits))
            channels.append({
                "channel": "mobile" if is_mobile else "phone",
                "value": phone,
                "source": lead.get("phone_source") or "legacy_migration",
                "confidence": 0.75 if is_mobile else 0.7,
                "notes": None,
            })

        email = lead.get("email")
        if email:
            generic_prefixes = ("info@", "kontakt@", "office@", "kanzlei@", "service@", "mail@", "buero@")
            is_generic = any(email.lower().startswith(p) for p in generic_prefixes)
            channels.append({
                "channel": "email",
                "value": email,
                "source": "legacy_migration",
                "confidence": 0.5 if is_generic else 0.7,
                "notes": "generic inbox" if is_generic else None,
            })

        if not channels:
            no_data += 1
            print(f"  - {lead['id'][:8]} — no legacy data, skipped")
            continue

        sb.table("leads").update({"contact_channels": channels}).eq("id", lead["id"]).execute()
        updated += 1
        print(f"  + {lead['id'][:8]} — {len(channels)} channels")

    print()
    print(f"Updated: {updated}")
    print(f"Skipped (already had channels): {skipped}")
    print(f"No-data (no legacy phone/email): {no_data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
