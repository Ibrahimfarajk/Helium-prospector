"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Filter, Search, X, ChevronDown, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn, formatRelative, statusLabel } from "@/lib/utils";
import type { Lead, LeadStatus, LeadTier } from "@/lib/db/types";

type SortKey = "posterior" | "created" | "freshness" | "name";

export function LeadsTable({ initialLeads }: { initialLeads: Lead[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const tier = params.get("tier") as LeadTier | null;
  const status = params.get("status") as LeadStatus | null;

  const [search, setSearch] = useState(params.get("q") || "");
  const [sortKey, setSortKey] = useState<SortKey>("posterior");
  const [activeIdx, setActiveIdx] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);

  // Volltext-Suche client-seitig (initialLeads schon eingegrenzt)
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = !q
      ? initialLeads
      : initialLeads.filter((l) =>
          [
            l.person_last_name,
            l.person_first_name,
            l.trigger_summary,
            l.hook_text,
            l.phone,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(q),
        );
    list = [...list].sort((a, b) => {
      switch (sortKey) {
        case "posterior":
          return b.posterior_score - a.posterior_score;
        case "freshness":
          return a.trigger_freshness_days - b.trigger_freshness_days;
        case "created":
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case "name":
          return (a.person_last_name || "").localeCompare(b.person_last_name || "");
      }
    });
    return list;
  }, [initialLeads, search, sortKey]);

  // Keyboard-Shortcuts: j/k navigation, / focus search, Enter open
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // ignore when typing in an input
      const t = e.target as HTMLElement;
      const inField =
        t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable;

      if (e.key === "/" && !inField) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (inField) return;

      if (e.key === "j") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter" && filtered[activeIdx]) {
        router.push(`/leads/${filtered[activeIdx].id}`);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, activeIdx, router]);

  const tiers: { v: LeadTier | "all"; label: string }[] = [
    { v: "all", label: "Alle" },
    { v: "t1", label: "T1" },
    { v: "t2", label: "T2" },
    { v: "t3", label: "T3" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-2.5 top-2.5 size-4 text-[var(--muted-foreground)]" />
          <Input
            ref={searchRef}
            placeholder="Suche Name, Firma, Trigger…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-8"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        <div className="flex items-center rounded-md border border-[var(--border)] p-0.5">
          {tiers.map((t) => {
            const active = (tier ?? "all") === t.v;
            return (
              <button
                key={t.v}
                onClick={() => {
                  const usp = new URLSearchParams(params.toString());
                  if (t.v === "all") usp.delete("tier");
                  else usp.set("tier", t.v);
                  router.push(`/leads?${usp.toString()}`);
                }}
                className={cn(
                  "h-7 px-3 text-xs rounded transition-colors",
                  active
                    ? "bg-[var(--accent)] text-[var(--foreground)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-xs text-[var(--muted-foreground)]">Sort</span>
          <div className="flex items-center rounded-md border border-[var(--border)] p-0.5">
            {([
              { v: "posterior", label: "Score" },
              { v: "freshness", label: "Frische" },
              { v: "created", label: "Datum" },
              { v: "name", label: "Name" },
            ] as const).map((s) => (
              <button
                key={s.v}
                onClick={() => setSortKey(s.v as SortKey)}
                className={cn(
                  "h-7 px-2.5 text-xs rounded transition-colors",
                  sortKey === s.v
                    ? "bg-[var(--accent)] text-[var(--foreground)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {filtered.length === 0 ? <EmptyList /> : <Table leads={filtered} activeIdx={activeIdx} />}

      <div className="text-[10px] text-[var(--muted-foreground)] flex items-center gap-3 pt-2">
        <span>
          <kbd className="text-[10px] font-mono">j/k</kbd> navigieren
        </span>
        <span>
          <kbd className="text-[10px] font-mono">Enter</kbd> öffnen
        </span>
        <span>
          <kbd className="text-[10px] font-mono">/</kbd> suchen
        </span>
      </div>
    </div>
  );
}

function Table({ leads, activeIdx }: { leads: Lead[]; activeIdx: number }) {
  return (
    <div className="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--card)]">
      <table className="w-full">
        <thead className="bg-[var(--muted)]/30 border-b border-[var(--border)]">
          <tr className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
            <th className="text-left px-4 py-2.5 font-medium w-14">Tier</th>
            <th className="text-left px-4 py-2.5 font-medium">Person · Firma</th>
            <th className="text-left px-4 py-2.5 font-medium">Trigger</th>
            <th className="text-right px-4 py-2.5 font-medium">Frische</th>
            <th className="text-right px-4 py-2.5 font-medium">Score</th>
            <th className="text-left px-4 py-2.5 font-medium">Status</th>
            <th className="w-2" />
          </tr>
        </thead>
        <tbody>
          {leads.map((l, i) => (
            <tr
              key={l.id}
              className={cn(
                "border-b border-[var(--border)] last:border-0 group transition-colors",
                i === activeIdx ? "bg-[var(--accent)]/40" : "hover:bg-[var(--accent)]/30",
              )}
            >
              <td className="px-4 py-3 align-middle">
                <Badge variant={l.tier as "t1" | "t2" | "t3"}>{l.tier.toUpperCase()}</Badge>
              </td>
              <td className="px-4 py-3 align-middle min-w-0">
                <Link href={`/leads/${l.id}`} className="block min-w-0">
                  <div className="text-sm font-medium truncate">
                    {[l.person_first_name, l.person_last_name].filter(Boolean).join(" ")}
                  </div>
                  <div className="text-xs text-[var(--muted-foreground)] truncate">
                    {l.trigger_summary.split(" — ").slice(0, 2).join(" — ")}
                  </div>
                </Link>
              </td>
              <td className="px-4 py-3 align-middle">
                <div className="text-xs">
                  {l.hook_text.length > 60 ? l.hook_text.slice(0, 60) + "…" : l.hook_text}
                </div>
              </td>
              <td className="px-4 py-3 align-middle text-right tabular-nums">
                <span className="text-xs text-[var(--muted-foreground)]">
                  {l.trigger_freshness_days}d
                </span>
              </td>
              <td className="px-4 py-3 align-middle text-right tabular-nums">
                <span className="text-sm font-medium">{(l.posterior_score * 100).toFixed(1)}%</span>
              </td>
              <td className="px-4 py-3 align-middle">
                <Badge variant={statusVariant(l.status)}>{statusLabel(l.status)}</Badge>
              </td>
              <td>
                <Link
                  href={`/leads/${l.id}`}
                  className="block size-full px-2"
                  aria-label="Lead öffnen"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function statusVariant(s: LeadStatus): "status-new" | "status-contacted" | "status-meeting" | "status-won" | "status-lost" {
  switch (s) {
    case "contacted":
    case "in_conversation":
    case "reviewing":
      return "status-contacted";
    case "meeting_set":
      return "status-meeting";
    case "closed_won":
      return "status-won";
    case "closed_lost":
    case "do_not_contact":
      return "status-lost";
    default:
      return "status-new";
  }
}

function EmptyList() {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border)] p-12 text-center">
      <Sparkles className="size-8 mx-auto text-[var(--muted-foreground)] mb-3" />
      <h3 className="text-sm font-medium mb-1">Keine Leads gefunden</h3>
      <p className="text-xs text-[var(--muted-foreground)]">
        Versuch andere Filter oder warte auf den nächsten Pipeline-Run.
      </p>
    </div>
  );
}
