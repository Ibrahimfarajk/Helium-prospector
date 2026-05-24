import Link from "next/link";
import { ArrowUpRight, Sparkles, TrendingUp, Users, Zap } from "lucide-react";

import { fetchDashboardStats, fetchLeads } from "@/lib/db/queries";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [stats, recentLeads] = await Promise.all([
    fetchDashboardStats(),
    fetchLeads({ tier: "t1" }),
  ]);

  const kpis = [
    {
      label: "Top-Leads (T1)",
      value: stats.byTier.t1,
      icon: Sparkles,
      accent: "text-[var(--tier-1)]",
      href: "/leads?tier=t1",
    },
    {
      label: "Frische Trigger ≤7 T",
      value: stats.freshThisWeek,
      icon: Zap,
      accent: "text-[var(--primary)]",
      href: "/leads",
    },
    {
      label: "Gesamt aktiv",
      value: stats.total,
      icon: Users,
      accent: "text-[var(--foreground)]",
      href: "/leads",
    },
    {
      label: "Conversion",
      value:
        stats.byStatus.closed_won + stats.byStatus.closed_lost === 0
          ? "—"
          : `${Math.round(stats.conversionRate * 100)}%`,
      icon: TrendingUp,
      accent: "text-[var(--foreground)]",
      href: "/leads?status=closed_won",
    },
  ];

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-7xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Übersicht deiner aktiven Lead-Pipeline.
        </p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <Link key={kpi.label} href={kpi.href} className="group">
              <Card className="p-5 transition-colors duration-150 group-hover:bg-[var(--accent)]/30">
                <div className="flex items-start justify-between">
                  <Icon className={`size-4 ${kpi.accent}`} />
                  <ArrowUpRight className="size-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-[var(--muted-foreground)]" />
                </div>
                <div className="mt-4 tabular-nums">
                  <div className="text-3xl font-semibold tracking-tight">{kpi.value}</div>
                  <p className="text-xs text-[var(--muted-foreground)] mt-1">{kpi.label}</p>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>

      {/* Tier-Übersicht */}
      <section className="space-y-3">
        <h2 className="text-sm font-medium tracking-tight text-[var(--muted-foreground)] uppercase">
          Tier-Verteilung
        </h2>
        <Card className="p-5">
          <TierBars stats={stats} />
        </Card>
      </section>

      {/* Heute zu bearbeiten */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-tight text-[var(--muted-foreground)] uppercase">
            Top-Leads heute
          </h2>
          <Link
            href="/leads?tier=t1"
            className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            Alle anzeigen →
          </Link>
        </div>

        {recentLeads.length === 0 ? (
          <Card className="p-12 text-center">
            <Sparkles className="size-8 mx-auto text-[var(--muted-foreground)] mb-3" />
            <h3 className="text-sm font-medium mb-1">Noch keine Top-Leads</h3>
            <p className="text-xs text-[var(--muted-foreground)]">
              Die Pipeline liefert ab dem nächsten Run um 06:00 Berlin-Zeit neue T1-Leads.
            </p>
          </Card>
        ) : (
          <Card className="divide-y divide-[var(--border)] overflow-hidden">
            {recentLeads.slice(0, 5).map((l) => (
              <Link
                key={l.id}
                href={`/leads/${l.id}`}
                className="flex items-center justify-between gap-4 p-4 hover:bg-[var(--accent)]/30 transition-colors duration-150"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {l.is_gold ? (
                    <Badge variant="gold">🎯 GOLD</Badge>
                  ) : (
                    <Badge variant={l.tier as "t1" | "t2" | "t3"}>{l.tier.toUpperCase()}</Badge>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {[l.person_first_name, l.person_last_name].filter(Boolean).join(" ")}
                    </p>
                    <p className="text-xs text-[var(--muted-foreground)] truncate">
                      {l.trigger_summary} · vor {l.trigger_freshness_days} Tagen
                    </p>
                  </div>
                </div>
                <div className="text-right shrink-0 tabular-nums">
                  <div className="text-xs font-medium">
                    {(l.posterior_score * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-[var(--muted-foreground)]">
                    {formatRelative(l.created_at)}
                  </div>
                </div>
              </Link>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}

function TierBars({ stats }: { stats: Awaited<ReturnType<typeof fetchDashboardStats>> }) {
  const total = stats.total || 1;
  const segments = [
    { tier: "t1" as const, count: stats.byTier.t1, color: "bg-[var(--tier-1)]", label: "T1" },
    { tier: "t2" as const, count: stats.byTier.t2, color: "bg-[var(--tier-2)]", label: "T2" },
    { tier: "t3" as const, count: stats.byTier.t3, color: "bg-[var(--tier-3)]", label: "T3" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex h-1.5 rounded-full overflow-hidden bg-[var(--muted)]">
        {segments.map((s) => (
          <div
            key={s.tier}
            className={s.color}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4 tabular-nums">
        {segments.map((s) => (
          <div key={s.tier}>
            <div className="flex items-center gap-2">
              <div className={`size-2 rounded-full ${s.color}`} />
              <span className="text-xs text-[var(--muted-foreground)]">{s.label}</span>
            </div>
            <div className="mt-1 text-lg font-semibold">{s.count}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
