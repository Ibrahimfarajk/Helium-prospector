"use client";

import { Suspense, useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, Mail, ArrowRight, Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-svh" />}>
      <LoginInner />
    </Suspense>
  );
}

function LoginInner() {
  const [email, setEmail] = useState("");
  const [emailSent, setEmailSent] = useState(false);
  const [pending, startTransition] = useTransition();
  const search = useSearchParams();
  const redirect = search.get("redirect") || "/";

  function isValidEmail(s: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!isValidEmail(trimmed)) {
      toast.error("Bitte gültige Email-Adresse eingeben");
      return;
    }
    startTransition(async () => {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithOtp({
        email: trimmed,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(redirect)}`,
        },
      });
      if (error) {
        toast.error("Login fehlgeschlagen", { description: error.message });
        return;
      }
      setEmailSent(true);
    });
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6 bg-gradient-to-br from-[var(--background)] via-[var(--background)] to-[oklch(0.18_0.02_152_/_0.5)]">
      <div className="w-full max-w-md animate-[slide-up_0.3s_ease-out]">
        <div className="mb-8 flex items-center justify-center gap-2">
          <div className="size-9 rounded-lg bg-[var(--primary)] flex items-center justify-center">
            <Sparkles className="size-5 text-[var(--primary-foreground)]" />
          </div>
          <span className="text-xl font-semibold tracking-tight">helium-prospector</span>
        </div>

        <Card className="shadow-2xl">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Anmelden</CardTitle>
            <CardDescription>
              {emailSent
                ? "Magic-Link wurde versendet"
                : "Wir senden dir einen Magic-Link per Email"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {emailSent ? (
              <div className="text-center space-y-4 py-2">
                <div className="mx-auto size-12 rounded-full bg-[oklch(0.7_0.17_152_/_0.15)] flex items-center justify-center">
                  <Mail className="size-6 text-[oklch(0.78_0.16_152)]" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm">
                    Wir haben einen Login-Link an{" "}
                    <span className="font-medium">{email}</span> geschickt.
                  </p>
                  <p className="text-xs text-[var(--muted-foreground)]">
                    Klick den Link in der Email, um dich anzumelden.
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                  onClick={() => {
                    setEmailSent(false);
                    setEmail("");
                  }}
                >
                  Andere Email-Adresse verwenden
                </Button>
              </div>
            ) : (
              <form onSubmit={onSubmit} className="space-y-3">
                <Input
                  type="email"
                  autoFocus
                  placeholder="name@firma.de"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={pending}
                  required
                />
                <Button type="submit" className="w-full" disabled={pending || !email.trim()}>
                  {pending ? (
                    <>
                      <Loader2 className="size-4 mr-2 animate-spin" />
                      Sende Magic-Link…
                    </>
                  ) : (
                    <>
                      Magic-Link senden
                      <ArrowRight className="size-4 ml-2" />
                    </>
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-xs text-[var(--muted-foreground)] mt-6">
          Closer-Account? Email genügt, falls vom Admin freigeschaltet.
        </p>
      </div>
    </div>
  );
}
