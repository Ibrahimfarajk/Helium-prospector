# GitHub-Actions Secrets — einmaliges Setup

> Damit der Daily-Cron-Pipeline in Supabase schreiben kann.

---

## Schritte

1. github.com → `Ibrahimfarajk/Helium-prospector` → **Settings** (oben rechts)
2. Links: **Secrets and variables** → **Actions**
3. **"New repository secret"** für jeden:

| Secret-Name | Wert |
|---|---|
| `SUPABASE_URL` | `https://jkqgpfbnplthchifwhqy.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | (aus deiner lokalen `pipeline/.env`) |
| `SUPABASE_ANON_KEY` | (für Keep-Alive-Job optional) |
| `DISCORD_WEBHOOK_URL` | (optional: Notification bei Fehlern) |

4. **Save** für jeden

---

## Verifikation

1. GitHub → Actions-Tab → "Daily Lead Pipeline" → "Run workflow"
2. Wähle Branch `main` → "Run workflow"
3. ~2-3 Min später: ✅ grüner Haken → Pipeline läuft

Erste echte Daten landen in Supabase via Cron am nächsten Morgen 05:00 UTC.

---

## Discord-Webhook für Alerts (optional, aber empfohlen)

Pre-Mortem-Mitigation: Bei Captcha-Block oder Pipeline-Fail bekommst du Push-Notification.

1. Discord öffnen → eigenen Server (oder neuen anlegen)
2. Channel anlegen z.B. `#helium-alerts`
3. Channel-Settings (Zahnrad) → Integrations → Webhooks → New Webhook
4. Copy Webhook-URL
5. GitHub Secret `DISCORD_WEBHOOK_URL` setzen
