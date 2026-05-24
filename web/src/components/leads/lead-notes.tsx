"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { MessageSquare, Loader2, Send } from "lucide-react";

import type { LeadActivity } from "@/lib/db/types";
import { addNote } from "@/app/(app)/leads/[id]/actions";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatRelative } from "@/lib/utils";

const ACTIVITY_LABEL: Record<string, string> = {
  status_change: "Status geändert",
  note_added: "Notiz",
  call_attempted: "Anruf versucht",
  call_completed: "Anruf geführt",
  email_sent: "Email gesendet",
  meeting_scheduled: "Termin vereinbart",
  document_sent: "Dokument gesendet",
  assigned: "Zugewiesen",
  reassigned: "Neu zugewiesen",
};

export function LeadNotes({
  leadId,
  activities,
}: {
  leadId: string;
  activities: LeadActivity[];
}) {
  const [note, setNote] = useState("");
  const [pending, startTransition] = useTransition();

  function submit() {
    if (!note.trim()) return;
    const optimistic = note;
    setNote("");
    startTransition(async () => {
      try {
        const r = await addNote(leadId, optimistic);
        if (r.ok) toast.success("Notiz gespeichert");
        else throw new Error();
      } catch {
        setNote(optimistic);
        toast.error("Notiz konnte nicht gespeichert werden");
      }
    });
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium">Aktivität & Notizen</h2>
        <span className="text-[10px] text-[var(--muted-foreground)]">
          {activities.length} Einträge
        </span>
      </div>

      <div className="space-y-2 mb-4">
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Notiz hinzufügen…  (Cmd+Enter speichert)"
          rows={2}
          className="w-full rounded-md border border-[var(--border)] bg-transparent p-3 text-sm placeholder:text-[var(--muted-foreground)] resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)]"
        />
        <div className="flex justify-end">
          <Button size="sm" onClick={submit} disabled={pending || !note.trim()}>
            {pending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <>
                <Send className="size-3.5 mr-1.5" />
                Speichern
              </>
            )}
          </Button>
        </div>
      </div>

      {activities.length === 0 ? (
        <div className="text-center py-8 text-xs text-[var(--muted-foreground)]">
          <MessageSquare className="size-6 mx-auto mb-2 opacity-40" />
          Noch keine Aktivität.
        </div>
      ) : (
        <ol className="space-y-3 border-l border-[var(--border)] pl-4 ml-1">
          {activities.map((a) => (
            <li key={a.id} className="relative">
              <div className="absolute -left-[19px] top-1 size-2.5 rounded-full bg-[var(--background)] border-2 border-[var(--border)]" />
              <div className="flex items-baseline gap-2 text-[10px] text-[var(--muted-foreground)] uppercase tracking-wider mb-0.5">
                <span>{ACTIVITY_LABEL[a.activity_type] ?? a.activity_type}</span>
                <span>·</span>
                <span>{formatRelative(a.created_at)}</span>
              </div>
              {a.note_md && (
                <p className="text-xs whitespace-pre-wrap text-[var(--foreground)]">
                  {a.note_md}
                </p>
              )}
              {a.payload && a.activity_type === "status_change" && (
                <p className="text-xs text-[var(--muted-foreground)]">
                  {String(a.payload.from ?? "—")} → <span className="text-[var(--foreground)]">{String(a.payload.to ?? "—")}</span>
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
