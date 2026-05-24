"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Check, ChevronRight, Loader2 } from "lucide-react";

import type { LeadStatus } from "@/lib/db/types";
import { updateLeadStatus } from "@/app/(app)/leads/[id]/actions";
import { cn, statusLabel } from "@/lib/utils";

const PIPELINE: LeadStatus[] = [
  "new",
  "reviewing",
  "contacted",
  "in_conversation",
  "meeting_set",
];

const TERMINAL: { status: LeadStatus; label: string; variant: "won" | "lost" }[] = [
  { status: "closed_won", label: "Gewonnen", variant: "won" },
  { status: "closed_lost", label: "Verloren", variant: "lost" },
];

export function LeadStatusPipeline({
  leadId,
  status,
}: {
  leadId: string;
  status: LeadStatus;
}) {
  const [pending, startTransition] = useTransition();
  const [optimisticStatus, setOptimisticStatus] = useState<LeadStatus>(status);

  const currentIdx = PIPELINE.indexOf(optimisticStatus);

  function set(s: LeadStatus) {
    if (s === optimisticStatus) return;
    setOptimisticStatus(s);
    startTransition(async () => {
      try {
        await updateLeadStatus(leadId, s);
        toast.success(`Status: ${statusLabel(s)}`);
      } catch (e) {
        setOptimisticStatus(status);
        toast.error("Status konnte nicht geändert werden");
      }
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center">
        {PIPELINE.map((s, idx) => {
          const done = idx < currentIdx || s === optimisticStatus;
          const active = s === optimisticStatus;
          return (
            <button
              key={s}
              onClick={() => set(s)}
              disabled={pending}
              className={cn(
                "flex-1 group flex flex-col items-center gap-1.5",
                pending && "opacity-50",
              )}
            >
              <div
                className={cn(
                  "size-7 rounded-full flex items-center justify-center text-[10px] font-medium border-2 transition-all",
                  active
                    ? "bg-[var(--primary)] border-[var(--primary)] text-[var(--primary-foreground)]"
                    : done
                      ? "bg-[var(--primary)]/20 border-[var(--primary)]/40 text-[var(--primary)]"
                      : "border-[var(--border)] text-[var(--muted-foreground)] group-hover:border-[var(--primary)]/50",
                )}
              >
                {done && !active ? <Check className="size-3.5" /> : idx + 1}
              </div>
              <span
                className={cn(
                  "text-[10px]",
                  active ? "text-[var(--foreground)] font-medium" : "text-[var(--muted-foreground)]",
                )}
              >
                {statusLabel(s)}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2 pt-3 border-t border-[var(--border)]">
        <span className="text-xs text-[var(--muted-foreground)] mr-2">Abschluss:</span>
        {TERMINAL.map((t) => (
          <button
            key={t.status}
            onClick={() => set(t.status)}
            disabled={pending}
            className={cn(
              "h-7 px-3 text-xs rounded-md border transition-colors",
              optimisticStatus === t.status
                ? t.variant === "won"
                  ? "bg-[var(--status-won)]/20 border-[var(--status-won)]/40 text-[var(--status-won)]"
                  : "bg-[var(--muted)] border-[var(--border)] text-[var(--muted-foreground)]"
                : "border-[var(--border)] hover:bg-[var(--accent)]",
            )}
          >
            {t.label}
          </button>
        ))}
        {pending && <Loader2 className="size-3 animate-spin text-[var(--muted-foreground)] ml-auto" />}
      </div>
    </div>
  );
}
