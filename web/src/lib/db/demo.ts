/**
 * Demo-Daten für UI-Screenshots/Demos ohne echte Supabase-Verbindung.
 *
 * Aktiviert via NEXT_PUBLIC_DEMO_MODE=true in .env.local.
 * In Production-Builds wird `isDemoMode()` zur Build-Time auf `false` evaluiert
 * (NEXT_PUBLIC_DEMO_MODE wird inlined), die unteren Fixtures werden tree-shaked.
 */

import type { Lead, LeadActivity, CrawlRun } from "./types";

export const DEMO_MODE: boolean = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function isDemoMode(): boolean {
  return DEMO_MODE;
}

const today = "2026-05-24";
const yesterday = "2026-05-23";

export function demoLeads(): Lead[] {
  return [
    mkLead({
      id: "demo-001",
      tier: "t1",
      score: 0.34,
      first: "Markus",
      last: "Krause",
      role: "Geschäftsführer",
      phone: "+49 89 123456-78",
      phone_source: "firmen-impressum",
      city: "München",
      hrb: "HRB 12345",
      court: "München",
      trigger_type: "shareholder_change",
      trigger_date: "2026-05-12",
      freshness: 12,
      summary:
        "2026-05-12 — Anteilseignerwechsel im HRB 12345 — (München)",
      hook: 'Frischer Anteilseignerwechsel — neuer Liquiditätszufluss wahrscheinlich. Idealer Anschluss: „Sie haben sich gerade neu ausgerichtet…',
      status: "new",
      created: today,
    }),
    mkLead({
      id: "demo-002",
      tier: "t1",
      score: 0.27,
      first: "Wolfgang",
      last: "Becker",
      role: "Geschäftsführer",
      phone: "(089) 230018-111",
      phone_source: "firmen-impressum",
      city: "München",
      hrb: "HRB 244393",
      court: "München",
      trigger_type: "new_registration",
      trigger_date: "2026-05-20",
      freshness: 4,
      summary: "2026-05-20 — Neueintragung im HRB 244393 — (München)",
      hook: 'Holding-Neueintragung — klares Indiz für Vermögens-Strukturierung. „Sie haben gerade eine Holding aufgesetzt…',
      status: "contacted",
      created: yesterday,
    }),
    mkLead({
      id: "demo-003",
      tier: "t1",
      score: 0.18,
      first: "Karin",
      last: "Fischer",
      role: "Geschäftsführerin",
      phone: "+49 941 569 54 651",
      phone_source: "firmen-impressum",
      city: "Regensburg",
      hrb: "HRB 241294",
      court: "Regensburg",
      trigger_type: "shareholder_change",
      trigger_date: "2026-05-17",
      freshness: 7,
      summary: "2026-05-17 — Anteilseignerwechsel im HRB 241294 — (Regensburg)",
      hook: "Frischer Exit nach 18 Jahren — Cash auf dem Konto, sucht aktiv Wiederanlage.",
      status: "in_conversation",
      created: yesterday,
    }),
    mkLead({
      id: "demo-004",
      tier: "t2",
      score: 0.094,
      first: "Andrea",
      last: "Schäfer",
      role: "Geschäftsführerin",
      phone: "+49 40 654321",
      phone_source: "firmen-impressum",
      city: "Hamburg",
      hrb: "HRB 78901",
      court: "Hamburg",
      trigger_type: "capital_increase",
      trigger_date: "2026-05-09",
      freshness: 15,
      summary: "2026-05-09 — Kapitalerhöhung im HRB 78901 — (Hamburg)",
      hook: "Kapitalerhöhung — frisches Eigenkapital im Unternehmen, häufig vor Diversifikation.",
      status: "meeting_set",
      created: "2026-05-21",
    }),
    mkLead({
      id: "demo-005",
      tier: "t2",
      score: 0.074,
      first: "Stefan",
      last: "Hoffmann",
      role: "Gesellschafter",
      phone: "+49 711 88290",
      phone_source: "firmen-impressum",
      city: "Stuttgart",
      hrb: "HRB 55432",
      court: "Stuttgart",
      trigger_type: "shareholder_change",
      trigger_date: "2026-05-02",
      freshness: 22,
      summary: "2026-05-02 — Anteilseignerwechsel im HRB 55432 — (Stuttgart)",
      hook: 'Anteilseignerwechsel vor 3 Wochen — Cash sucht Anlage.',
      status: "reviewing",
      created: "2026-05-20",
    }),
    mkLead({
      id: "demo-006",
      tier: "t3",
      score: 0.046,
      first: "Petra",
      last: "Wagner",
      role: "Geschäftsführerin",
      phone: "+49 30 28447300",
      phone_source: "firmen-impressum",
      city: "Berlin",
      hrb: "HRB 198765",
      court: "Berlin (Charlottenburg)",
      trigger_type: "gf_change",
      trigger_date: "2026-05-15",
      freshness: 9,
      summary: "2026-05-15 — Geschäftsführerwechsel im HRB 198765 — (Berlin)",
      hook: "GF-Wechsel — möglicher Exit oder Generations-Übergang.",
      status: "new",
      created: "2026-05-22",
    }),
    mkLead({
      id: "demo-007",
      tier: "t3",
      score: 0.038,
      first: "Thomas",
      last: "Richter",
      role: "Geschäftsführer",
      phone: "+49 221 12345-67",
      phone_source: "firmen-impressum",
      city: "Köln",
      hrb: "HRB 88123",
      court: "Köln",
      trigger_type: "gf_change",
      trigger_date: "2026-05-11",
      freshness: 13,
      summary: "2026-05-11 — Geschäftsführerwechsel im HRB 88123 — (Köln)",
      hook: "Strukturelle Veränderung — Investment-Allokation kann sich verschieben.",
      status: "closed_lost",
      created: "2026-05-19",
    }),
    mkLead({
      id: "demo-008",
      tier: "t1",
      score: 0.21,
      first: "Klaus",
      last: "König",
      role: "Geschäftsführer",
      phone: "+49 69 13899830",
      phone_source: "firmen-impressum",
      city: "Frankfurt am Main",
      hrb: "HRB 92841",
      court: "Frankfurt am Main",
      trigger_type: "shareholder_change",
      trigger_date: "2026-05-19",
      freshness: 5,
      summary: "2026-05-19 — Anteilseignerwechsel im HRB 92841 — (Frankfurt)",
      hook: 'Frischer Exit (5 Tage) + Süd-DE — Wiederanlage steht oben auf der Agenda.',
      status: "closed_won",
      created: "2026-05-22",
    }),
  ];
}

export function demoActivities(leadId: string): LeadActivity[] {
  if (leadId !== "demo-001") return [];
  return [
    {
      id: "act-3",
      lead_id: leadId,
      user_id: "demo-admin",
      activity_type: "note_added",
      note_md:
        "StB-Termin am Donnerstag bestätigt. Hat speziell nach §6b-Reinvestitionsrücklage gefragt — Material gesendet.",
      payload: null,
      created_at: "2026-05-23T15:20:00Z",
    },
    {
      id: "act-2",
      lead_id: leadId,
      user_id: "demo-admin",
      activity_type: "status_change",
      payload: { from: "contacted", to: "in_conversation" },
      note_md: null,
      created_at: "2026-05-23T11:08:00Z",
    },
    {
      id: "act-1",
      lead_id: leadId,
      user_id: "demo-admin",
      activity_type: "call_completed",
      note_md:
        "Erstgespräch 14 Min. Offen für Direktbeteiligung. Holding gerade gegründet, ist im Steuer-Optimierungs-Modus.",
      payload: null,
      created_at: "2026-05-23T10:45:00Z",
    },
  ];
}

export function demoRuns(): CrawlRun[] {
  return [
    mkRun(0, "success", 42, 8, 0),
    mkRun(1, "success", 38, 5, 0),
    mkRun(2, "success", 51, 11, 0),
    mkRun(3, "captcha", 12, 0, 2, "Captcha-Block ab Seite 3 — manual restart nötig."),
    mkRun(4, "success", 45, 7, 0),
    mkRun(5, "success", 33, 4, 0),
    mkRun(6, "success", 49, 9, 0),
  ];
}

// ───────────────────────────────────────────────────────────────────

function mkLead(p: {
  id: string;
  tier: "t1" | "t2" | "t3";
  score: number;
  first: string;
  last: string;
  role: string;
  phone: string;
  phone_source: string;
  city: string;
  hrb: string;
  court: string;
  trigger_type: Lead["trigger_type"];
  trigger_date: string;
  freshness: number;
  summary: string;
  hook: string;
  status: Lead["status"];
  created: string;
}): Lead {
  return {
    id: p.id,
    bekanntmachung_id: null,
    company_id: null,
    person_first_name: p.first,
    person_last_name: p.last,
    person_role: p.role,
    person_appointed_at: p.trigger_date,
    phone: p.phone,
    phone_source: p.phone_source,
    email: null,
    trigger_type: p.trigger_type,
    trigger_date: p.trigger_date,
    trigger_summary: p.summary,
    trigger_freshness_days: p.freshness,
    posterior_score: p.score,
    tier: p.tier,
    score_breakdown: {
      prior: 0.001,
      likelihood_ratios: {
        trigger_shareholder_change_0_9mo: 10,
        ek_ge_2m: 8,
        freshness_lt_7d: p.freshness < 7 ? 5 : 4,
        name_contains_holding: 4,
      },
      posterior: p.score,
      tier: p.tier,
      hard_gates_passed: true,
      hard_gates_failed_reasons: [],
    },
    status: p.status,
    assigned_to: null,
    assigned_at: null,
    best_call_window: "Di/Mi 10:00–12:00 oder 14:30–16:00",
    dossier_markdown: buildDossier(p),
    hook_text: p.hook,
    objection_handles: [
      { objection: "Woher meine Nummer?", response: "Firmen-Impressum öffentlich" },
      {
        objection: "Helium klingt nach NASCO",
        response: "Star Oil Hamburg, ORRI direkt, keine Aktie",
      },
      { objection: "Steuerlich komplex", response: "DBA US-DE, §15 EStG, abgedeckt" },
    ],
    do_not_contact: false,
    do_not_contact_reason: null,
    deleted_at: null,
    created_at: p.created + "T08:00:00Z",
    updated_at: p.created + "T08:00:00Z",
  };
}

function buildDossier(p: {
  id: string;
  tier: string;
  score: number;
  first: string;
  last: string;
  role: string;
  city: string;
  hrb: string;
  court: string;
  trigger_date: string;
  freshness: number;
  hook: string;
  summary: string;
}): string {
  return `# LEAD ${p.id} | Posterior ${p.score.toFixed(2)} | Tier ${p.tier.toUpperCase()}

**Person:** ${p.first} ${p.last}
**Rolle:** ${p.role} · ${p.city}
**HRB:** ${p.hrb} (${p.court})

## Trigger (warum jetzt)
${p.summary} — Trigger-Frische: ${p.freshness} Tage.

## Hook für Opener
${p.hook}

## Erwartete Einwände (Top 3)
1. "Woher meine Nummer?" → Firmen-Impressum öffentlich
2. "Helium klingt nach NASCO" → Star Oil Hamburg, ORRI direkt
3. "Steuerlich komplex" → DBA US-DE, §15 EStG, abgedeckt

## Belege
- HR-Eintrag ${p.hrb}
- Bundesanzeiger JA 2024 (geprüft)
`;
}

function mkRun(
  daysAgo: number,
  status: string,
  found: number,
  leads: number,
  captchas: number,
  err?: string,
): CrawlRun {
  const date = new Date("2026-05-24T05:00:00Z");
  date.setDate(date.getDate() - daysAgo);
  return {
    id: `run-${daysAgo}`,
    started_at: date.toISOString(),
    finished_at: new Date(date.getTime() + 18 * 60 * 1000).toISOString(),
    status,
    pages_fetched: 5,
    captchas_hit: captchas,
    bekanntmachungen_found: found,
    leads_created: leads,
    error_message: err ?? null,
    notes: null,
  };
}
