"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, ListTodo, Settings, Sparkles, Activity } from "lucide-react";

import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: ListTodo },
  { href: "/runs", label: "Pipeline", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--background)]">
      <div className="flex h-14 items-center gap-2 px-4 border-b border-[var(--border)]">
        <div className="size-7 rounded-md bg-[var(--primary)] flex items-center justify-center">
          <Sparkles className="size-4 text-[var(--primary-foreground)]" />
        </div>
        <span className="text-sm font-semibold tracking-tight">helium-prospector</span>
      </div>

      <nav className="flex-1 px-2 py-4 space-y-0.5">
        {nav.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-all duration-150",
                isActive
                  ? "bg-[var(--accent)] text-[var(--foreground)] font-medium shadow-sm"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--accent)]/70",
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t border-[var(--border)]">
        <kbd className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
          <span className="text-[11px] mr-1">⌘</span>K
          <span className="ml-1 normal-case">Suche</span>
        </kbd>
      </div>
    </aside>
  );
}
