import { createClient } from "@/lib/supabase/server";
import type { Lead, LeadActivity, LeadTier, LeadStatus, CrawlRun } from "./types";
import { isDemoMode, demoLeads, demoActivities, demoRuns } from "./demo";

// ───────────────────────────────────────────────────────────────────
// Wrapper: bypass Supabase Type-Inference (Database-types werden zur
// Compile-Zeit nicht voll resolved bei manuell geschriebenen Types).
// Types werden via expliziten Casts garantiert.
// ───────────────────────────────────────────────────────────────────

async function db() {
  const supabase = await createClient();
  return supabase as unknown as {
    // Supabase-SSR-Generic-Type-Inference-Bug — wir cast .from() bewusst auf any
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    from: (table: string) => any;
  };
}

// ───────────────────────────────────────────────────────────────────
// Dashboard-Queries
// ───────────────────────────────────────────────────────────────────

export type DashboardStats = {
  total: number;
  byTier: Record<LeadTier, number>;
  byStatus: Record<LeadStatus, number>;
  freshThisWeek: number;
  conversionRate: number; // closed_won / (closed_won + closed_lost)
};

export async function fetchDashboardStats(): Promise<DashboardStats> {
  if (isDemoMode()) return demoStats();
  const supabase = await db();
  const { data } = await supabase
    .from("leads_view")
    .select("tier, status, trigger_freshness_days")
    .is("deleted_at", null);

  const all = (data ?? []) as Array<{
    tier: LeadTier;
    status: LeadStatus;
    trigger_freshness_days: number;
  }>;

  const byTier: Record<LeadTier, number> = { t1: 0, t2: 0, t3: 0 };
  const byStatus: Record<LeadStatus, number> = {
    new: 0,
    reviewing: 0,
    contacted: 0,
    in_conversation: 0,
    meeting_set: 0,
    closed_won: 0,
    closed_lost: 0,
    do_not_contact: 0,
  };

  let freshThisWeek = 0;
  for (const l of all) {
    byTier[l.tier] = (byTier[l.tier] ?? 0) + 1;
    byStatus[l.status] = (byStatus[l.status] ?? 0) + 1;
    if (l.trigger_freshness_days <= 7) freshThisWeek++;
  }

  const won = byStatus.closed_won;
  const lost = byStatus.closed_lost;
  const conversionRate = won + lost === 0 ? 0 : won / (won + lost);

  return { total: all.length, byTier, byStatus, freshThisWeek, conversionRate };
}

function demoStats(): DashboardStats {
  const all = demoLeads();
  const byTier: Record<LeadTier, number> = { t1: 0, t2: 0, t3: 0 };
  const byStatus: Record<LeadStatus, number> = {
    new: 0,
    reviewing: 0,
    contacted: 0,
    in_conversation: 0,
    meeting_set: 0,
    closed_won: 0,
    closed_lost: 0,
    do_not_contact: 0,
  };
  let freshThisWeek = 0;
  for (const l of all) {
    byTier[l.tier]++;
    byStatus[l.status]++;
    if (l.trigger_freshness_days <= 7) freshThisWeek++;
  }
  const won = byStatus.closed_won;
  const lost = byStatus.closed_lost;
  return {
    total: all.length,
    byTier,
    byStatus,
    freshThisWeek,
    conversionRate: won + lost === 0 ? 0 : won / (won + lost),
  };
}

// ───────────────────────────────────────────────────────────────────
// Lead-Queries
// ───────────────────────────────────────────────────────────────────

export type LeadFilters = {
  tier?: LeadTier;
  status?: LeadStatus;
  search?: string;
};

export async function fetchLeads(filters: LeadFilters = {}): Promise<Lead[]> {
  if (isDemoMode()) {
    let list = demoLeads();
    if (filters.tier) list = list.filter((l) => l.tier === filters.tier);
    if (filters.status) list = list.filter((l) => l.status === filters.status);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      list = list.filter((l) =>
        [l.person_last_name, l.person_first_name, l.trigger_summary]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    return list;
  }
  const supabase = await db();
  let query = supabase
    .from("leads_view")
    .select("*")
    .is("deleted_at", null)
    .order("posterior_score", { ascending: false });

  if (filters.tier) query = query.eq("tier", filters.tier);
  if (filters.status) query = query.eq("status", filters.status);

  const { data, error } = await query;
  if (error) {
    console.error("fetchLeads failed", error);
    return [];
  }

  const all = (data ?? []) as Lead[];
  if (!filters.search) return all;

  const q = filters.search.toLowerCase();
  return all.filter(
    (l) =>
      l.person_last_name.toLowerCase().includes(q) ||
      (l.person_first_name?.toLowerCase().includes(q) ?? false) ||
      l.trigger_summary.toLowerCase().includes(q),
  );
}

export async function fetchLeadById(id: string): Promise<Lead | null> {
  if (isDemoMode()) return demoLeads().find((l) => l.id === id) ?? null;
  const supabase = await db();
  const { data } = await supabase
    .from("leads_view")
    .select("*")
    .eq("id", id)
    .is("deleted_at", null)
    .single();
  return (data ?? null) as Lead | null;
}

export async function fetchActivities(leadId: string): Promise<LeadActivity[]> {
  if (isDemoMode()) return demoActivities(leadId);
  const supabase = await db();
  const { data } = await supabase
    .from("lead_activities")
    .select("*")
    .eq("lead_id", leadId)
    .order("created_at", { ascending: false });
  return (data ?? []) as LeadActivity[];
}

export async function fetchRecentCrawlRuns(limit = 10): Promise<CrawlRun[]> {
  if (isDemoMode()) return demoRuns().slice(0, limit);
  const supabase = await db();
  const { data } = await supabase
    .from("crawl_runs")
    .select("*")
    .order("started_at", { ascending: false })
    .limit(limit);
  return (data ?? []) as CrawlRun[];
}
