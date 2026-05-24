import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(d: string | Date | null | undefined): string {
  if (!d) return "—";
  const date = typeof d === "string" ? new Date(d) : d;
  return date.toLocaleDateString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatRelative(d: string | Date | null | undefined): string {
  if (!d) return "—";
  const date = typeof d === "string" ? new Date(d) : d;
  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return formatDate(d); // Future date → exact date
  if (diffDays === 0) return "heute";
  if (diffDays === 1) return "gestern";
  if (diffDays < 7) return `vor ${diffDays} Tagen`;
  if (diffDays < 30) return `vor ${Math.floor(diffDays / 7)} Wochen`;
  return formatDate(d);
}

export function formatEur(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

export function tierLabel(tier: "t1" | "t2" | "t3"): string {
  return { t1: "T1", t2: "T2", t3: "T3" }[tier];
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    new: "Neu",
    reviewing: "Review",
    contacted: "Kontaktiert",
    in_conversation: "Im Gespräch",
    meeting_set: "Termin",
    closed_won: "Gewonnen",
    closed_lost: "Verloren",
    do_not_contact: "DnC",
  };
  return labels[status] ?? status;
}
