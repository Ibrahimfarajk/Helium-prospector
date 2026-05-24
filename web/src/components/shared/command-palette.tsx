"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  LayoutDashboard,
  ListTodo,
  RefreshCcw,
  Settings,
  Search,
  FileText,
  Activity,
} from "lucide-react";

const items = [
  {
    group: "Navigation",
    items: [
      { id: "dashboard", label: "Dashboard öffnen", icon: LayoutDashboard, action: "nav:/" },
      { id: "leads", label: "Alle Leads", icon: ListTodo, action: "nav:/leads" },
      { id: "leads-t1", label: "Top-Leads (T1)", icon: ListTodo, action: "nav:/leads?tier=t1" },
      { id: "runs", label: "Pipeline-Runs", icon: Activity, action: "nav:/runs" },
      { id: "settings", label: "Einstellungen", icon: Settings, action: "nav:/settings" },
    ],
  },
  {
    group: "Aktionen",
    items: [
      { id: "export", label: "Tagesplan exportieren (PDF)", icon: FileText, action: "noop:export-pdf" },
      { id: "refresh", label: "Pipeline neu starten", icon: RefreshCcw, action: "noop:trigger-pipeline" },
    ],
  },
];

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState("");

  useEffect(() => {
    if (!open) setValue("");
  }, [open]);

  function runAction(action: string) {
    onOpenChange(false);
    if (action.startsWith("nav:")) router.push(action.slice(4));
    // andere Aktionen: implementiert je nach Feature in Phase 3.9 / 4
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4 bg-black/50 backdrop-blur-sm animate-[fade-in_0.15s_ease-out]"
      onClick={() => onOpenChange(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl rounded-xl border border-[var(--border)] bg-[var(--popover)] shadow-2xl overflow-hidden animate-[slide-up_0.2s_ease-out]"
      >
        <Command label="Command" className="text-sm" shouldFilter>
          <div className="flex items-center gap-2 px-3 border-b border-[var(--border)]">
            <Search className="size-4 text-[var(--muted-foreground)]" />
            <Command.Input
              value={value}
              onValueChange={setValue}
              placeholder="Aktion suchen oder Lead-Name eingeben…"
              autoFocus
              className="flex-1 h-12 bg-transparent border-0 outline-none placeholder:text-[var(--muted-foreground)]"
            />
            <kbd className="text-[10px] font-mono text-[var(--muted-foreground)] hidden md:inline">
              ESC
            </kbd>
          </div>

          <Command.List className="max-h-[420px] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-xs text-[var(--muted-foreground)]">
              Keine Treffer für „{value}"
            </Command.Empty>

            {items.map((group) => (
              <Command.Group
                key={group.group}
                heading={group.group}
                className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] px-2 py-1.5"
              >
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Command.Item
                      key={item.id}
                      value={`${item.label} ${item.id}`}
                      onSelect={() => runAction(item.action)}
                      className="flex items-center gap-2.5 px-2.5 py-2 rounded-md cursor-pointer text-sm text-[var(--foreground)] aria-selected:bg-[var(--accent)] aria-selected:text-[var(--accent-foreground)] transition-colors"
                    >
                      <Icon className="size-4 text-[var(--muted-foreground)]" />
                      {item.label}
                    </Command.Item>
                  );
                })}
              </Command.Group>
            ))}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}

export function useCmdK(setOpen: (v: boolean | ((v: boolean) => boolean)) => void) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [setOpen]);
}
