import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const { data: profileRaw } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", user!.id)
    .single();
  const profile = profileRaw as { email: string; role: string; full_name: string | null } | null;

  return (
    <div className="p-6 md:p-8 max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Einstellungen</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Account-Info und System-Konfiguration.
        </p>
      </header>

      <Card className="p-5 space-y-3">
        <h2 className="text-sm font-medium">Account</h2>
        <dl className="grid grid-cols-3 gap-2 text-sm">
          <dt className="text-[var(--muted-foreground)]">Email</dt>
          <dd className="col-span-2">{profile?.email ?? user!.email}</dd>
          <dt className="text-[var(--muted-foreground)]">Rolle</dt>
          <dd className="col-span-2">
            <Badge variant={profile?.role === "admin" ? "status-won" : "default"}>
              {profile?.role ?? "—"}
            </Badge>
          </dd>
          <dt className="text-[var(--muted-foreground)]">Name</dt>
          <dd className="col-span-2">{profile?.full_name ?? "—"}</dd>
        </dl>
      </Card>

      <Card className="p-5 space-y-3">
        <h2 className="text-sm font-medium">System</h2>
        <dl className="grid grid-cols-3 gap-2 text-sm">
          <dt className="text-[var(--muted-foreground)]">Pipeline-Schedule</dt>
          <dd className="col-span-2 font-mono text-xs">Daily 05:00 UTC (07:00 Berlin)</dd>
          <dt className="text-[var(--muted-foreground)]">Quelle</dt>
          <dd className="col-span-2">handelsregister.de Bekanntmachungen</dd>
          <dt className="text-[var(--muted-foreground)]">Bayes-Threshold</dt>
          <dd className="col-span-2 tabular-nums">
            T1 ≥ 15% · T2 ≥ 5% · T3 ≥ 1%
          </dd>
        </dl>
      </Card>
    </div>
  );
}
