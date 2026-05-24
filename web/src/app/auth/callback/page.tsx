"use client";

/**
 * Auth-Callback Client-Page für Implicit-Flow (Token im URL-Fragment).
 *
 * Supabase Magic-Link / OTP / Admin-Generated-Links liefern Token im Fragment
 * (`#access_token=...&refresh_token=...`). Server-Route kann Fragment nicht sehen
 * — daher Client-Komponente die das Fragment parst und Session setzt.
 *
 * PKCE-Flow (signInWithOtp → ?code=...) wird parallel von /auth/callback/route.ts
 * gehandled.
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";

export default function AuthCallbackPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const supabase = createClient();

      // Variante A: Fragment-based (#access_token=... von Magic-Link/OTP)
      if (typeof window !== "undefined" && window.location.hash) {
        const hash = new URLSearchParams(window.location.hash.slice(1));
        const access_token = hash.get("access_token");
        const refresh_token = hash.get("refresh_token");
        if (access_token && refresh_token) {
          const { error } = await supabase.auth.setSession({
            access_token,
            refresh_token,
          });
          if (error) {
            setErr(error.message);
            return;
          }
          // Hash entfernen + redirect
          const next = search.get("next") || "/";
          router.replace(next);
          return;
        }
      }

      // Variante B: PKCE ?code=... (signInWithOtp)
      const code = search.get("code");
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          setErr(error.message);
          return;
        }
        const next = search.get("next") || "/";
        router.replace(next);
        return;
      }

      setErr("Kein Auth-Token in URL gefunden.");
    })();
  }, [router, search]);

  return (
    <div className="min-h-svh flex items-center justify-center">
      <div className="text-center space-y-3">
        {err ? (
          <>
            <p className="text-sm text-[var(--destructive)]">{err}</p>
            <a href="/login" className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              ← Zur Login-Seite
            </a>
          </>
        ) : (
          <>
            <Loader2 className="size-6 mx-auto animate-spin text-[var(--muted-foreground)]" />
            <p className="text-xs text-[var(--muted-foreground)]">Anmeldung läuft…</p>
          </>
        )}
      </div>
    </div>
  );
}
