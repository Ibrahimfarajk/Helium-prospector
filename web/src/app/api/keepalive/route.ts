/**
 * Keep-Alive Endpoint — verhindert Supabase-Pause nach 7 Tagen Inaktivität.
 * Wird von Vercel Cron 1x/Tag gepingt (siehe vercel.json).
 *
 * Pre-Mortem-Mitigation U4 (siehe docs/PRE_MORTEM.md).
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const supabase = await createClient();
    // Trivialer Touch — hält DB aktiv
    const { error } = await supabase
      .from("crawl_runs")
      .select("id")
      .limit(1);

    if (error) {
      return NextResponse.json(
        { status: "error", error: error.message },
        { status: 500 },
      );
    }

    return NextResponse.json({
      status: "alive",
      timestamp: new Date().toISOString(),
    });
  } catch (e) {
    return NextResponse.json(
      { status: "error", error: String(e) },
      { status: 500 },
    );
  }
}
