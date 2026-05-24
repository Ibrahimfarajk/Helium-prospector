import { NextRequest, NextResponse } from "next/server";

import { fetchLeads } from "@/lib/db/queries";
import type { LeadTier, LeadStatus } from "@/lib/db/types";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const tier = url.searchParams.get("tier") as LeadTier | null;
  const status = url.searchParams.get("status") as LeadStatus | null;
  const leads = await fetchLeads({
    tier: tier ?? undefined,
    status: status ?? undefined,
  });

  const headers = [
    "tier",
    "score",
    "person_first_name",
    "person_last_name",
    "person_role",
    "phone",
    "trigger_type",
    "trigger_date",
    "trigger_freshness_days",
    "status",
    "created_at",
  ];
  const rows = leads.map((l) =>
    [
      l.tier,
      l.posterior_score.toFixed(4),
      escape(l.person_first_name ?? ""),
      escape(l.person_last_name),
      escape(l.person_role ?? ""),
      escape(l.phone ?? ""),
      l.trigger_type,
      l.trigger_date,
      String(l.trigger_freshness_days),
      l.status,
      l.created_at,
    ].join(","),
  );

  const csv = [headers.join(","), ...rows].join("\n");
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="leads-${new Date().toISOString().slice(0, 10)}.csv"`,
    },
  });
}

function escape(s: string): string {
  if (!s.includes(",") && !s.includes('"') && !s.includes("\n")) return s;
  return `"${s.replace(/"/g, '""')}"`;
}
