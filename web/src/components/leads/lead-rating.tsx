"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { ThumbsUp, Minus, ThumbsDown, Loader2 } from "lucide-react";

import { rateLead, type LeadRating } from "@/app/(app)/leads/[id]/actions";
import { cn } from "@/lib/utils";

const RATINGS: Array<{ v: LeadRating; label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = [
  { v: "top", label: "Top-Lead", icon: ThumbsUp, color: "text-[var(--status-won)]" },
  { v: "ok", label: "OK", icon: Minus, color: "text-[var(--muted-foreground)]" },
  { v: "schlecht", label: "Schlecht", icon: ThumbsDown, color: "text-[var(--destructive)]" },
];

export function LeadRating({ leadId, currentRating }: { leadId: string; currentRating?: LeadRating }) {
  const [active, setActive] = useState<LeadRating | undefined>(currentRating);
  const [pending, startTransition] = useTransition();

  function submit(rating: LeadRating) {
    const prev = active;
    setActive(rating);
    startTransition(async () => {
      try {
        await rateLead(leadId, rating);
        toast.success(`Bewertung gespeichert: ${rating}`);
      } catch {
        setActive(prev);
        toast.error("Bewertung fehlgeschlagen");
      }
    });
  }

  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
        Closer-Bewertung
      </div>
      <div className="flex gap-1.5">
        {RATINGS.map((r) => {
          const Icon = r.icon;
          const isActive = active === r.v;
          return (
            <button
              key={r.v}
              onClick={() => submit(r.v)}
              disabled={pending}
              className={cn(
                "flex-1 flex flex-col items-center gap-1 py-2 px-2 rounded-md border transition-all",
                "text-[10px]",
                isActive
                  ? "border-[var(--ring)] bg-[var(--accent)] shadow-sm"
                  : "border-[var(--border)] hover:bg-[var(--accent)]/50 text-[var(--muted-foreground)]",
              )}
            >
              <Icon className={cn("size-4", isActive ? r.color : "")} />
              <span className={isActive ? "font-medium" : ""}>{r.label}</span>
            </button>
          );
        })}
      </div>
      {pending && (
        <div className="flex items-center gap-1.5 text-[10px] text-[var(--muted-foreground)]">
          <Loader2 className="size-3 animate-spin" /> Speichere…
        </div>
      )}
      <p className="text-[10px] text-[var(--muted-foreground)] pt-1">
        Fließt in Bayes-Re-Kalibrierung ein. Admin sieht Aggregate in Settings.
      </p>
    </div>
  );
}
