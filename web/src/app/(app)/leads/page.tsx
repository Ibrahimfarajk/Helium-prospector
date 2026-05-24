import { fetchLeads } from "@/lib/db/queries";
import { LeadsTable } from "@/components/leads/leads-table";
import type { LeadTier, LeadStatus } from "@/lib/db/types";

export const dynamic = "force-dynamic";

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<{ tier?: string; status?: string; q?: string }>;
}) {
  const params = await searchParams;
  const tier = params.tier as LeadTier | undefined;
  const status = params.status as LeadStatus | undefined;
  const search = params.q;

  const leads = await fetchLeads({ tier, status, search });

  return (
    <div className="p-6 md:p-8 max-w-7xl">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {leads.length} {leads.length === 1 ? "Lead" : "Leads"}
            {tier && ` · Tier ${tier.toUpperCase()}`}
            {status && ` · Status ${status}`}
            {search && ` · Suche "${search}"`}
          </p>
        </div>
      </header>

      <LeadsTable initialLeads={leads} />
    </div>
  );
}
