"use server";

import { revalidatePath } from "next/cache";

import { createClient } from "@/lib/supabase/server";
import type { LeadStatus } from "@/lib/db/types";

export async function updateLeadStatus(leadId: string, status: LeadStatus) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("not_authenticated");

  // Lade alten Status für audit
  const { data: prev } = (await supabase
    .from("leads")
    .select("status")
    .eq("id", leadId)
    .single()) as { data: { status: LeadStatus } | null };

  const { error } = await (supabase.from("leads") as any)
    .update({ status })
    .eq("id", leadId);
  if (error) throw new Error(error.message);

  // Activity-Eintrag
  await (supabase.from("lead_activities") as any).insert({
    lead_id: leadId,
    user_id: user.id,
    activity_type: "status_change",
    payload: { from: prev?.status, to: status },
  });

  // Audit-Log
  await (supabase.from("audit_log") as any).insert({
    user_id: user.id,
    action: "lead.status_change",
    resource_type: "lead",
    resource_id: leadId,
    payload: { from: prev?.status, to: status },
  });

  revalidatePath(`/leads/${leadId}`);
  revalidatePath("/leads");
  revalidatePath("/");
  return { ok: true };
}

export async function addNote(leadId: string, note: string) {
  if (!note.trim()) return { ok: false, error: "empty" };
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("not_authenticated");

  await (supabase.from("lead_activities") as any).insert({
    lead_id: leadId,
    user_id: user.id,
    activity_type: "note_added",
    note_md: note.trim(),
  });

  revalidatePath(`/leads/${leadId}`);
  return { ok: true };
}

export type LeadRating = "top" | "ok" | "schlecht";

export async function rateLead(leadId: string, rating: LeadRating, note?: string) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("not_authenticated");

  await (supabase.from("lead_activities") as any).insert({
    lead_id: leadId,
    user_id: user.id,
    activity_type: "lead_rated",
    payload: { rating },
    note_md: note?.trim() || null,
  });

  await (supabase.from("audit_log") as any).insert({
    user_id: user.id,
    action: "lead.rated",
    resource_type: "lead",
    resource_id: leadId,
    payload: { rating },
  });

  revalidatePath(`/leads/${leadId}`);
  return { ok: true };
}

export async function markDoNotContact(leadId: string, reason: string) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("not_authenticated");

  await (supabase.from("leads") as any)
    .update({
      do_not_contact: true,
      do_not_contact_reason: reason || "user-requested",
      status: "do_not_contact",
    })
    .eq("id", leadId);

  await (supabase.from("audit_log") as any).insert({
    user_id: user.id,
    action: "lead.dnc",
    resource_type: "lead",
    resource_id: leadId,
    payload: { reason },
  });

  revalidatePath(`/leads/${leadId}`);
  revalidatePath("/leads");
  return { ok: true };
}
