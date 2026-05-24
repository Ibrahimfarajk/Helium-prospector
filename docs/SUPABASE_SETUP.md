# Supabase-Setup — Schritt für Schritt

> Einmalig in ~5-10 Min. Danach läuft alles automatisch.

---

## 1. Projekt anlegen

1. [supabase.com](https://supabase.com/) öffnen → "Start your project" / "New Project"
2. Sign-in mit GitHub (empfohlen) oder Email
3. **Free-Plan** auswählen
4. New Project:
   - **Name:** `helium-prospector`
   - **Database Password:** *generiere ein starkes Passwort und speichere es im Passwort-Manager — du brauchst es ggf. bei direktem DB-Zugriff*
   - **Region:** Europe Central (Frankfurt) — kürzeste Latenz für DACH-User
   - **Plan:** Free
5. ~2 Min warten bis Projekt provisioned ist

---

## 2. Schema importieren

1. Im Dashboard links: **SQL Editor** → "New query"
2. Inhalt von `shared/db_schema.sql` reinkopieren (die ganze Datei)
3. **Run** klicken (rechts unten oder Cmd/Ctrl+Enter)
4. Erwartete Meldung: "Success. No rows returned."

**Verification:**
- Links **Database** → **Tables** → solltest sehen:
  - `profiles`, `bekanntmachungen_raw`, `companies`, `leads`,
  - `lead_assignments`, `lead_activities`, `audit_log`, `crawl_runs`

---

## 3. Auth-Konfiguration

1. Links: **Authentication** → **Providers**
2. **Email** Provider:
   - ✅ enabled (default)
   - **Confirm email:** ✅ on (Magic-Link braucht das nicht, aber empfohlen für Sicherheit)
   - **Secure email change:** ✅ on
3. **Authentication** → **URL Configuration**:
   - **Site URL:** für lokale Dev `http://localhost:3000`, später ändern auf Vercel-URL
   - **Redirect URLs:** auch beide hinzufügen
4. **Authentication** → **Email Templates** (optional, aber nett):
   - "Magic Link" → personalisieren mit "helium-prospector" als Absender

---

## 4. Admin-User anlegen

1. **Authentication** → **Users** → "Add user" → "Create new user"
2. **Email:** `ibrahimk94@outlook.de`
3. **Auto Confirm User:** ✅ ja
4. (kein Passwort nötig wenn Magic-Link)
5. User-ID kopieren (uuid, z.B. `abc12345-...`)
6. Zurück zu **SQL Editor**, neue Query:
   ```sql
   insert into profiles (id, email, role, full_name)
   values (
     '<DEINE-USER-ID>',          -- aus Authentication → Users
     'ibrahimk94@outlook.de',
     'admin',
     'Ibrahim K.'
   );
   ```
7. Run

---

## 5. Credentials für `.env` holen

1. Im Dashboard: **Settings** (Zahnrad-Icon links unten) → **API**
2. Kopiere folgende Werte:

   | Field auf Supabase | Trägt in deine `.env` als |
   |---|---|
   | **Project URL** | `SUPABASE_URL` UND `NEXT_PUBLIC_SUPABASE_URL` |
   | **anon / public key** | `SUPABASE_ANON_KEY` UND `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
   | **service_role key** (KLICK "Reveal") | `SUPABASE_SERVICE_ROLE_KEY` ⚠️ **niemals frontend-side!** |

3. Im Repo-Root `.env` Datei erstellen (falls noch nicht):
   ```bash
   cp .env.example .env
   ```
4. Werte eintragen.

---

## 6. Test der Verbindung

Aus dem Repo-Root:

```powershell
cd web
pnpm install
pnpm dev
```

Browser öffnen: `http://localhost:3000` → Login-Seite sollte erscheinen.

Bei Login mit `ibrahimk94@outlook.de` → Magic-Link-Email kommt → Klick → Dashboard.

---

## Häufige Probleme

- **"Invalid login credentials":** User noch nicht in `profiles` eingetragen (Schritt 4)
- **Email kommt nicht:** Spam-Ordner checken. Supabase Free-Tier-SMTP ist langsam (~30 s) und nutzt eigene Domain — Whitelist `noreply@mail.app.supabase.io`
- **RLS-Errors:** Schema sauber importiert? Siehe Verification in Schritt 2

---

## Sicherheit — sehr wichtig

- **`service_role_key`** hat root-Zugriff auf die ganze DB. **Nur** in:
  - `.env` lokal (nicht committet)
  - GitHub Secrets (für Pipeline)
  - Server-Side Code (`app/api/*`, server actions)
- **NIEMALS:**
  - im Frontend-Code (`NEXT_PUBLIC_*` ist sichtbar im Browser-Bundle!)
  - im GitHub-Repo (selbst Private)
  - in Logs
