import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { AppShell } from "@/components/shared/app-shell";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Demo-Mode bypass für Screenshots / Live-Demos
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
    return (
      <AppShell user={{ email: "demo@helium-prospector.de", role: "admin", full_name: "Ibrahim K." }}>
        {children}
      </AppShell>
    );
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  // Profile aus profiles-Tabelle holen
  const { data: profileRaw } = await supabase
    .from("profiles")
    .select("email, role, full_name")
    .eq("id", user.id)
    .single();

  const profile = profileRaw as { email: string; role: string; full_name: string | null } | null;

  const userInfo = {
    email: profile?.email ?? user.email ?? "",
    role: profile?.role ?? "closer",
    full_name: profile?.full_name ?? null,
  };

  return <AppShell user={userInfo}>{children}</AppShell>;
}
