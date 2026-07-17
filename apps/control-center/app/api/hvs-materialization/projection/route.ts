/**
 * Cohort 10D — HVS materialization projection (GET, read-only bridge).
 *
 * Same-origin, local-first read boundary. Returns the authoritative
 * materialization truth state + the deterministic plan for a prepared project.
 * No mutation, no HVS call, no external network, no browser-supplied path.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsMaterializationStore,
  hvsMaterializationStorePath,
} from "@/lib/hvs-materialization-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;

export async function GET(request: NextRequest) {
  const projectId = request.nextUrl.searchParams.get("projectId") ?? "";
  if (!SAFE_ID_PATTERN.test(projectId)) {
    return NextResponse.json(
      { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const store = new HvsMaterializationStore(hvsMaterializationStorePath());
  const result = store.readProjection(projectId);
  if (!result.ok || !result.projection) {
    const detail = result.error_code === "PERSISTENCE_WRITE_FAILED" ? "persistence unavailable" : result.detail;
    return NextResponse.json(
      { ok: false, error_code: result.error_code, detail },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(
    { ok: true, error_code: null, detail: null, projection: result.projection },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
