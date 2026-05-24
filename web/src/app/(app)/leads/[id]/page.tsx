import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Phone, Clock, FileText, AlertTriangle, Ban } from "lucide-react";

import { fetchLeadById, fetchActivities } from "@/lib/db/queries";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/utils";
import { LeadStatusPipeline } from "@/components/leads/lead-status-pipeline";
import { LeadNotes } from "@/components/leads/lead-notes";
import { LeadDossier } from "@/components/leads/lead-dossier";
import { LeadDangerActions } from "@/components/leads/lead-danger-actions";

export const dynamic = "force-dynamic";

export default async function LeadDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [lead, activities] = await Promise.all([fetchLeadById(id), fetchActivities(id)]);
  if (!lead) notFound();

  const fullName = [lead.person_first_name, lead.person_last_name].filter(Boolean).join(" ");

  return (
    <div className="p-6 md:p-8 max-w-5xl">
      <Link
        href="/leads"
        className="inline-flex items-center gap-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-6 transition-colors"
      >
        <ArrowLeft className="size-3" /> Zurück zur Liste
      </Link>

      <header className="mb-6 flex items-start justify-between gap-4">
        <div className="space-y-2 min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant={lead.tier as "t1" | "t2" | "t3"}>{lead.tier.toUpperCase()}</Badge>
            <span className="text-xs text-[var(--muted-foreground)] tabular-nums">
              Posterior {(lead.posterior_score * 100).toFixed(2)}%
            </span>
            <span className="text-xs text-[var(--muted-foreground)]">·</span>
            <span className="text-xs text-[var(--muted-foreground)]">
              Frische {lead.trigger_freshness_days} Tage
            </span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{fullName || "—"}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {lead.person_role && `${lead.person_role} · `}
            {lead.trigger_summary}
          </p>
        </div>
        <LeadDangerActions leadId={lead.id} dnc={lead.do_not_contact} />
      </header>

      {lead.do_not_contact && (
        <div className="mb-6 p-4 rounded-lg border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 flex items-start gap-3">
          <AlertTriangle className="size-4 text-[var(--destructive)] mt-0.5" />
          <div className="text-xs">
            <p className="font-medium text-[var(--destructive)]">Do-Not-Contact gesetzt</p>
            <p className="text-[var(--muted-foreground)] mt-0.5">
              {lead.do_not_contact_reason || "Kein Grund angegeben."}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* Phone + Best-call */}
          <Card className="p-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-1">
                  Telefon
                </div>
                <div className="flex items-center gap-2">
                  <Phone className="size-4 text-[var(--muted-foreground)]" />
                  {lead.phone ? (
                    <a
                      href={`tel:${lead.phone.replace(/[^+\d]/g, "")}`}
                      className="text-sm font-medium hover:text-[var(--primary)] transition-colors tabular-nums"
                    >
                      {lead.phone}
                    </a>
                  ) : (
                    <span className="text-sm text-[var(--muted-foreground)]">
                      nicht gefunden — Closer-Recherche nötig
                    </span>
                  )}
                </div>
                {lead.phone_source && (
                  <p className="text-[10px] text-[var(--muted-foreground)] mt-1 truncate">
                    Quelle: {lead.phone_source}
                  </p>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-1">
                  Beste Anrufzeit
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="size-4 text-[var(--muted-foreground)]" />
                  <span className="text-sm">{lead.best_call_window || "—"}</span>
                </div>
              </div>
            </div>
          </Card>

          {/* Dossier */}
          <Card className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium">Dossier</h2>
              <a
                href={`/leads/${lead.id}/export`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 h-7 px-2.5 text-xs rounded-md text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
              >
                <FileText className="size-3.5" />
                Druckansicht
              </a>
            </div>
            <LeadDossier markdown={lead.dossier_markdown} />
          </Card>

          {/* Status-Pipeline */}
          <Card className="p-5">
            <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
              Status
            </div>
            <LeadStatusPipeline leadId={lead.id} status={lead.status} />
          </Card>

          {/* Notes */}
          <LeadNotes leadId={lead.id} activities={activities} />
        </div>

        {/* Sidebar — Belege + Score-Details */}
        <div className="space-y-6">
          <Card className="p-5">
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
              Belege
            </h3>
            <ul className="space-y-2 text-xs">
              <li>
                <span className="text-[var(--muted-foreground)]">HR-Eintrag:</span>{" "}
                <span className="font-mono text-[var(--foreground)]">
                  {lead.trigger_summary}
                </span>
              </li>
              <li>
                <span className="text-[var(--muted-foreground)]">Trigger-Datum:</span>{" "}
                <span className="tabular-nums">{lead.trigger_date}</span>
              </li>
              <li>
                <span className="text-[var(--muted-foreground)]">Trigger-Typ:</span>{" "}
                <span>{lead.trigger_type}</span>
              </li>
            </ul>
          </Card>

          <Card className="p-5">
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
              Score-Aufschlüsselung
            </h3>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[var(--muted-foreground)]">Prior</span>
                <span className="tabular-nums">{lead.score_breakdown?.prior}</span>
              </div>
              {Object.entries(lead.score_breakdown?.likelihood_ratios || {}).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3">
                  <span className="text-[var(--muted-foreground)] truncate font-mono text-[10px]">
                    {k}
                  </span>
                  <span className="tabular-nums">×{Number(v).toFixed(1)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
                <span className="font-medium">Posterior</span>
                <span className="font-medium tabular-nums">
                  {(lead.posterior_score * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <h3 className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
              Metadata
            </h3>
            <ul className="space-y-1.5 text-xs">
              <li>
                <span className="text-[var(--muted-foreground)]">Erstellt:</span>{" "}
                {formatRelative(lead.created_at)}
              </li>
              <li>
                <span className="text-[var(--muted-foreground)]">Aktualisiert:</span>{" "}
                {formatRelative(lead.updated_at)}
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
