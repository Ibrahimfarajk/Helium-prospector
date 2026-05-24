"use client";

import { useState } from "react";
import { Search, LogOut, User2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function TopBar({
  user,
  onCmdK,
}: {
  user: { email: string; role: string; full_name?: string | null };
  onCmdK: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  }

  return (
    <header className="h-14 shrink-0 border-b border-[var(--border)] bg-[var(--background)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--background)]/60 sticky top-0 z-10">
      <div className="h-full flex items-center justify-between px-4 md:px-6">
        <button
          type="button"
          onClick={onCmdK}
          className={cn(
            "flex items-center gap-2 h-9 px-3 text-sm rounded-md",
            "border border-[var(--border)] text-[var(--muted-foreground)] bg-transparent",
            "hover:bg-[var(--accent)] hover:text-[var(--foreground)]",
            "transition-colors duration-150 w-full max-w-[280px]",
          )}
        >
          <Search className="size-4" />
          <span className="flex-1 text-left">Suchen oder Aktion…</span>
          <kbd className="hidden md:inline-flex text-[10px] font-mono opacity-70">
            ⌘K
          </kbd>
        </button>

        <div className="relative">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMenuOpen((v) => !v)}
            className="gap-2"
          >
            <div className="size-6 rounded-full bg-[var(--primary)]/15 text-[var(--primary)] flex items-center justify-center text-xs font-semibold">
              {(user.full_name || user.email).slice(0, 1).toUpperCase()}
            </div>
            <span className="hidden md:inline text-xs">
              {user.full_name || user.email.split("@")[0]}
            </span>
          </Button>

          {menuOpen && (
            <div
              className="absolute right-0 top-full mt-2 w-56 rounded-lg border border-[var(--border)] bg-[var(--popover)] shadow-xl py-1.5 animate-[fade-in_0.15s_ease-out]"
              onMouseLeave={() => setMenuOpen(false)}
            >
              <div className="px-3 py-2 border-b border-[var(--border)]">
                <p className="text-xs font-medium">{user.full_name || "—"}</p>
                <p className="text-[10px] text-[var(--muted-foreground)]">{user.email}</p>
                <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                  Rolle: <span className="text-[var(--foreground)]">{user.role}</span>
                </p>
              </div>
              <button
                onClick={signOut}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-[var(--accent)] transition-colors"
              >
                <LogOut className="size-3.5" />
                Abmelden
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
