import { NextRequest, NextResponse } from "next/server";

import { fetchLeadById } from "@/lib/db/queries";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const lead = await fetchLeadById(id);
  if (!lead) return new NextResponse("Not found", { status: 404 });

  // Print-friendly HTML — Browser kann es als PDF speichern
  // (Phase-3-MVP — Phase 4 ggf. server-side PDF mit @react-pdf/renderer)
  const html = `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Lead ${lead.id.slice(0, 8)}</title>
<style>
  @page { margin: 2cm; }
  body { font-family: Inter, system-ui, sans-serif; color: #111; max-width: 720px; margin: 0 auto; line-height: 1.5; font-size: 12pt; }
  h1 { font-size: 16pt; margin: 0 0 8px; }
  h2 { font-size: 10pt; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-top: 24px; }
  .meta { color: #666; font-size: 10pt; margin-bottom: 24px; }
  .tier { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 9pt; font-weight: 500; }
  .tier-t1 { background: #fee2e2; color: #991b1b; }
  .tier-t2 { background: #ffedd5; color: #9a3412; }
  .tier-t3 { background: #fef3c7; color: #92400e; }
  pre { white-space: pre-wrap; font-family: inherit; font-size: 11pt; }
</style>
</head>
<body>
<h1>${escapeHtml([lead.person_first_name, lead.person_last_name].filter(Boolean).join(" ") || "—")}</h1>
<div class="meta">
  <span class="tier tier-${lead.tier}">${lead.tier.toUpperCase()}</span>
  &middot; Posterior ${(lead.posterior_score * 100).toFixed(1)}%
  &middot; ${lead.trigger_summary}
</div>
<pre>${escapeHtml(lead.dossier_markdown)}</pre>
<h2>Belege</h2>
<ul>
  <li>HR-Eintrag: ${escapeHtml(lead.trigger_summary)}</li>
  <li>Trigger-Datum: ${lead.trigger_date}</li>
  <li>Telefon: ${escapeHtml(lead.phone || "—")}${lead.phone_source ? ` (${escapeHtml(lead.phone_source)})` : ""}</li>
</ul>
<script>window.print();</script>
</body>
</html>`;

  return new NextResponse(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Disposition": `inline; filename="lead-${lead.id.slice(0, 8)}.html"`,
    },
  });
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
