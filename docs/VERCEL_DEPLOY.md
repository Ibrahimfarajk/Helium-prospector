# Vercel-Deploy — Step by Step

> Einmaliger Setup, ~5 Min. Danach Auto-Deploy bei jedem `git push`.

---

## 1. Repo auf Vercel importieren

1. [vercel.com/new](https://vercel.com/new) öffnen
2. Sign-in mit GitHub (gleiches Konto wie das `Ibrahimfarajk` Repo)
3. **"Import"** beim `Helium-prospector` Repo klicken
4. Falls Vercel das Repo nicht sieht: "Adjust GitHub App Permissions" → Repo zugriff freigeben

---

## 2. Project konfigurieren

| Field | Wert |
|---|---|
| **Project Name** | `helium-prospector` (oder beliebig) |
| **Framework Preset** | Next.js (auto-detected) |
| **Root Directory** | **`web`** ⚠️ wichtig — anklicken und ändern, Default ist Repo-Root |
| **Build Command** | `next build` (default OK) |
| **Output Directory** | `.next` (default OK) |
| **Install Command** | `pnpm install --no-frozen-lockfile` |
| **Node.js Version** | 22.x oder 24.x |

---

## 3. Environment Variables

Klick auf **"Environment Variables"** und füge folgende ein (alle 4 Environments aktivieren: Production, Preview, Development):

```
NEXT_PUBLIC_SUPABASE_URL = https://jkqgpfbnplthchifwhqy.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY = eyJhbGc...8WYbnSfW8aNSjXefC1kw7jJ2omvIRDmiF3AnVNcU8x4
SUPABASE_URL = https://jkqgpfbnplthchifwhqy.supabase.co
SUPABASE_SERVICE_ROLE_KEY = eyJhbGc...UzPGWwsjazQsoc9po-zDsyxeVlXskdxESE9SGXQmHD8
NEXT_PUBLIC_DEMO_MODE = false
```

**Hinweis:** Die `SUPABASE_SERVICE_ROLE_KEY` ist sensitiv. Nicht im Frontend exponieren (kein `NEXT_PUBLIC_`-Prefix). Wird nur in Server Actions verwendet.

Werte aus deiner lokalen `.env.local` (in `/web/`).

---

## 4. Deploy

1. **"Deploy"** klicken
2. ~2-3 Min warten bis Build durchläuft
3. Live-URL kopieren (z.B. `helium-prospector-xxx.vercel.app`)

---

## 5. Supabase Redirect-URL ergänzen

**Wichtig** — sonst funktioniert Magic-Link-Login nicht:

1. Supabase-Dashboard → Authentication → **URL Configuration**
2. **Site URL:** ändere auf `https://helium-prospector-xxx.vercel.app`
3. **Redirect URLs:** füge hinzu:
   - `https://helium-prospector-xxx.vercel.app/**`
   - `http://localhost:3000/**` (für lokale Dev)
   - `http://localhost:3001/**` (falls 3000 belegt)
4. Save

---

## 6. Login-Test

1. Live-URL öffnen → wird auf `/login` redirected (Middleware)
2. Email `ibrahimk94@outlook.de` eintragen
3. "Magic-Link senden" klicken
4. Email-Inbox checken (Spam-Ordner auch)
5. Link klicken → landest im Dashboard mit 13 echten Leads aus der Pipeline-Test-Run

---

## 7. Auto-Deploy ist aktiv

Jeder `git push origin main` triggert auto einen Production-Deploy.
PR-Branches bekommen Preview-Deploys mit eigener URL.

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| "Module not found: @supabase/ssr" | Vercel Installation Command nicht gesetzt → `pnpm install --no-frozen-lockfile` |
| "Auth callback failed" | Supabase Redirect-URLs nicht ergänzt (Schritt 5) |
| Magic-Link kommt nicht | Spam-Ordner, dann Supabase Free-Tier-SMTP-Throttling (max 4 Emails/Stunde) |
| Build-Error TS | `tsconfig.json` strict-mode — alle TS-Errors müssen weg, sonst fail. `next build` lokal prüfen vorher |

---

## Custom Domain (optional, später)

In Vercel → Project Settings → Domains → Add Domain
- z.B. `app.helium.gmbh` (registriere bei INWX/Hetzner für ~10 EUR/Jahr)
- DNS: CNAME auf `cname.vercel-dns.com`
- HTTPS wird automatisch ausgestellt (Lets-Encrypt)

Standard-Subdomain `helium-prospector-xxx.vercel.app` ist für MVP völlig ausreichend.
