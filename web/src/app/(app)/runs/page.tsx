import { fetchRecentCrawlRuns } from "@/lib/db/queries";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function RunsPage() {
  const runs = await fetchRecentCrawlRuns(20);

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Pipeline-Runs</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Tägliche Crawl-Läufe + Telemetrie für Captcha-Frühwarnung.
        </p>
      </header>

      {runs.length === 0 ? (
        <Card className="p-12 text-center text-sm text-[var(--muted-foreground)]">
          Noch keine Runs.
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead className="bg-[var(--muted)]/30 border-b border-[var(--border)]">
              <tr className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
                <th className="text-left px-4 py-2.5 font-medium">Gestartet</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-right px-4 py-2.5 font-medium">Bekanntm.</th>
                <th className="text-right px-4 py-2.5 font-medium">Leads</th>
                <th className="text-right px-4 py-2.5 font-medium">Captchas</th>
                <th className="text-left px-4 py-2.5 font-medium">Notizen</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-4 py-3 text-xs">{formatRelative(r.started_at)}</td>
                  <td className="px-4 py-3 text-xs">
                    <Badge variant={r.status === "success" ? "status-won" : r.status === "captcha" ? "t1" : "status-new"}>
                      {r.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right text-xs tabular-nums">
                    {r.bekanntmachungen_found}
                  </td>
                  <td className="px-4 py-3 text-right text-xs tabular-nums">{r.leads_created}</td>
                  <td className="px-4 py-3 text-right text-xs tabular-nums">{r.captchas_hit}</td>
                  <td className="px-4 py-3 text-xs text-[var(--muted-foreground)] truncate max-w-xs">
                    {r.error_message || r.notes || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
