/**
 * Supabase-Schema-Types — mirror von shared/db_schema.sql.
 *
 * Später ersetzbar durch supabase gen types typescript --linked > types.ts
 * Für MVP: handgeschrieben, exakt am SQL-Schema entlang.
 */

export type LeadTier = "t1" | "t2" | "t3";

export type LeadStatus =
  | "new"
  | "reviewing"
  | "contacted"
  | "in_conversation"
  | "meeting_set"
  | "closed_won"
  | "closed_lost"
  | "do_not_contact";

export type BekanntmachungType =
  | "gf_change"
  | "shareholder_change"
  | "new_registration"
  | "capital_increase"
  | "other";

export type UserRole = "admin" | "closer";

export type ContactChannelKind =
  | "phone"
  | "mobile"
  | "email"
  | "linkedin"
  | "xing"
  | "website";

export type ContactChannel = {
  channel: ContactChannelKind;
  value: string;
  source: string;
  confidence: number;
  notes?: string | null;
};

export type CountryCode = "DE" | "AT" | "CH";

export type ActivityType =
  | "status_change"
  | "note_added"
  | "call_attempted"
  | "call_completed"
  | "email_sent"
  | "meeting_scheduled"
  | "document_sent"
  | "assigned"
  | "reassigned"
  | "lead_rated";

// ─────────────────────────────────────────────────────────────────────────

export type Profile = {
  id: string;
  email: string;
  role: UserRole;
  full_name: string | null;
  avatar_url: string | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Company = {
  id: string;
  hrb_nummer: string | null;
  register_court: string | null;
  legal_form: string | null;
  name: string;
  address: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: CountryCode;
  last_ja_year: number | null;
  equity_eur: number | null;
  balance_sum_eur: number | null;
  ja_fetched_at: string | null;
  has_holding_in_name: boolean;
  has_vermoegen_in_name: boolean;
  has_family_office_hint: boolean;
  has_us_business_hint: boolean;
  website: string | null;
  phone: string | null;
  impressum_url: string | null;
  created_at: string;
  updated_at: string;
};

export type Lead = {
  id: string;
  bekanntmachung_id: string | null;
  company_id: string | null;
  person_first_name: string | null;
  person_last_name: string;
  person_role: string | null;
  person_appointed_at: string | null;
  phone: string | null;
  phone_source: string | null;
  email: string | null;
  contact_channels: ContactChannel[];
  trigger_type: BekanntmachungType;
  trigger_date: string;
  trigger_summary: string;
  trigger_freshness_days: number;
  posterior_score: number;
  tier: LeadTier;
  score_breakdown: {
    prior: number;
    likelihood_ratios: Record<string, number>;
    posterior: number;
    tier: LeadTier;
    hard_gates_passed: boolean;
    hard_gates_failed_reasons: string[];
  };
  status: LeadStatus;
  assigned_to: string | null;
  assigned_at: string | null;
  best_call_window: string | null;
  dossier_markdown: string;
  hook_text: string;
  objection_handles: Array<{ objection: string; response: string }>;
  is_gold: boolean;
  gold_reason: string | null;
  do_not_contact: boolean;
  do_not_contact_reason: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type LeadActivity = {
  id: string;
  lead_id: string;
  user_id: string;
  activity_type: ActivityType;
  payload: Record<string, unknown> | null;
  note_md: string | null;
  created_at: string;
};

export type LeadAssignment = {
  id: string;
  lead_id: string;
  user_id: string;
  assigned_by: string | null;
  assigned_at: string;
  released_at: string | null;
  notes: string | null;
};

export type CrawlRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  pages_fetched: number;
  captchas_hit: number;
  bekanntmachungen_found: number;
  leads_created: number;
  error_message: string | null;
  notes: string | null;
};

// ─────────────────────────────────────────────────────────────────────────
// Supabase Database-Type (für createClient<Database>())
// ─────────────────────────────────────────────────────────────────────────

export type Database = {
  public: {
    Tables: {
      profiles: {
        Row: Profile;
        Insert: Omit<Profile, "created_at" | "updated_at"> & {
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Profile>;
      };
      companies: {
        Row: Company;
        Insert: Omit<Company, "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Company>;
      };
      leads: {
        Row: Lead;
        Insert: Omit<Lead, "id" | "created_at" | "updated_at" | "trigger_freshness_days"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Omit<Lead, "trigger_freshness_days">>;
      };
      lead_activities: {
        Row: LeadActivity;
        Insert: Omit<LeadActivity, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<LeadActivity>;
      };
      lead_assignments: {
        Row: LeadAssignment;
        Insert: Omit<LeadAssignment, "id" | "assigned_at"> & {
          id?: string;
          assigned_at?: string;
        };
        Update: Partial<LeadAssignment>;
      };
      crawl_runs: {
        Row: CrawlRun;
        Insert: Omit<CrawlRun, "id" | "started_at"> & {
          id?: string;
          started_at?: string;
        };
        Update: Partial<CrawlRun>;
      };
    };
    Enums: {
      lead_tier: LeadTier;
      lead_status: LeadStatus;
      bekanntmachung_type: BekanntmachungType;
      user_role: UserRole;
      activity_type: ActivityType;
    };
  };
};
