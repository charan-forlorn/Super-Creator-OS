/** Cohort 9B local-only safe dry-run preview route.
 * POST accepts one bounded dry-run request and returns a deterministic preview.
 * It does not read/write files, launch processes, invoke HVS, persist history,
 * access browser storage, open transports, or perform external egress.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { planOperatorDryRun } from "@/lib/operator-dry-run";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    payload = null;
  }
  return NextResponse.json(planOperatorDryRun(payload), {
    status: 200,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json",
    },
  });
}
