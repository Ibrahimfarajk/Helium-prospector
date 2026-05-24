"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Ban, Loader2 } from "lucide-react";

import { markDoNotContact } from "@/app/(app)/leads/[id]/actions";
import { Button } from "@/components/ui/button";

export function LeadDangerActions({
  leadId,
  dnc,
}: {
  leadId: string;
  dnc: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, startTransition] = useTransition();

  if (dnc) return null; // schon DnC → kein Button

  function submit() {
    startTransition(async () => {
      try {
        const r = await markDoNotContact(leadId, reason.trim());
        if (r.ok) {
          toast.success("Lead als Do-Not-Contact markiert");
          setOpen(false);
        }
      } catch {
        toast.error("Aktion fehlgeschlagen");
      }
    });
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        className="text-xs text-[var(--muted-foreground)] hover:text-[var(--destructive)] gap-1.5"
      >
        <Ban className="size-3.5" />
        DnC
      </Button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/50 backdrop-blur-sm animate-[fade-in_0.15s_ease-out]"
          onClick={() => !pending && setOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--popover)] p-5 shadow-2xl space-y-4 animate-[slide-up_0.2s_ease-out]"
          >
            <div className="flex items-start gap-3">
              <div className="size-9 shrink-0 rounded-md bg-[var(--destructive)]/10 flex items-center justify-center">
                <Ban className="size-4 text-[var(--destructive)]" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-medium">Do-Not-Contact setzen?</h3>
                <p className="text-xs text-[var(--muted-foreground)]">
                  Lead wird in keiner Liste mehr angezeigt. Action ist audit-log-tracked.
                </p>
              </div>
            </div>

            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Grund (optional, aber empfohlen für Audit)…"
              rows={2}
              className="w-full rounded-md border border-[var(--border)] bg-transparent p-2.5 text-xs placeholder:text-[var(--muted-foreground)] resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            />

            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOpen(false)}
                disabled={pending}
              >
                Abbrechen
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={submit}
                disabled={pending}
              >
                {pending ? <Loader2 className="size-3.5 animate-spin" /> : "Bestätigen"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
