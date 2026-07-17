/**
 * Cohort 10D — HVS materialization projection (GET, read-only bridge).
 *
 * Same-origin, local-first read boundary. Returns the authoritative
 * materialization truth state + the deterministic plan for a prepared project,
 * produced ENTIRELY by the Python authority through the bridge. No
 * mutation, no HVS call, no external network, no browser-supplied path.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsMaterializationStore,
  buildProjectionPayload,
  serverResolvedScope,
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

  const scope = serverResolvedScope();
  const store = new HvsMaterializationStore();
  const bridge = await store.invoke("projection", buildProjectionPayload({ projectId, storePath: scope.storePath }));
  if (!bridge.ok || !bridge.response) {
    return NextResponse.json(
      { ok: false, error_code: bridge.error_code ?? "BRIDGE_FAILED", detail: "projection unavailable" },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  const body = bridge.response;
  if (!body.ok || !body.projection) {
    return NextResponse.json(
      { ok: false, error_code: body.error_code ?? "PROJECT_NOT_FOUND", detail: body.detail ?? "no projection" },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(
    { ok: true, error_code: null, detail: null, projection: body.projection },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
