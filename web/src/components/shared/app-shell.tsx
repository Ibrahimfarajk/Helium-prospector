"use client";

import { useState } from "react";

import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";
import { CommandPalette, useCmdK } from "./command-palette";

export function AppShell({
  user,
  children,
}: {
  user: { email: string; role: string; full_name: string | null };
  children: React.ReactNode;
}) {
  const [cmdkOpen, setCmdkOpen] = useState(false);
  useCmdK(setCmdkOpen);

  return (
    <div className="flex h-svh">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar user={user} onCmdK={() => setCmdkOpen(true)} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
      <CommandPalette open={cmdkOpen} onOpenChange={setCmdkOpen} />
    </div>
  );
}
