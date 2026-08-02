/** SCOS R2.1 — pre-render readiness API route (§6.F).

 *  Read-only. The browser submits only the safe external project_ref; the server
 *  resolves canonical id + task-owned roots from environment. It must NOT create a
 *  render authorization or invoke a renderer. Root/identity fields are never
 *  accepted from the request body.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { invokeRenderReadiness } from "@/lib/paid-pilot-render-readiness-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX = 2048;
const REF_PATTERN = /^[A-Za-z0-9_-]{2,96}$/;
const FORBIDDEN_KEYS = new Set([
  "admission_store_path", "materialization_store_path", "hvs_projects_root", "output_root",
  "canonical_internal_project_id", "store_path", "evidence_base", "runtime_base",
]);

function safeError(code: string, detail: string, status = 400) {
  return NextResponse.json({ ok: false, state: "NOT_READY", error_code: code, detail, checks: [], projection: null }, { status, headers: { "cache-control": "no-store" } });
}

export async function POST(request: NextRequest) {
  let raw = "";
  try {
    const b = await request.arrayBuffer();
    if (b.byteLength > MAX) return safeError("REQUEST_TOO_LARGE", "payload exceeds limit", 413);
    raw = Buffer.from(b).toString("utf8");
  } catch {
    return safeError("REQUEST_UNREADABLE", "body unreadable");
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
  } catch {
    return safeError("REQUEST_MALFORMED", "invalid json");
  }
  const ref = typeof body.external_project_ref === "string" ? body.external_project_ref : "";
  if (!REF_PATTERN.test(ref)) return safeError("PROJECT_REF_MALFORMED", "invalid external_project_ref");
  // The browser submits ONLY the admitted external project_ref. The canonical
  // internal ID is derived server-side from the persisted authoritative mapping
  // (never trusted from the request body). The route forwards only the external
  // ref plus server-owned roots.
  const payload: Record<string, unknown> = { external_project_ref: ref };
  const SERVER_ROOT_KEYS: Record<string, string> = {
    admission_store_path: "SCOS_PILOT_PACKET_ADMISSION_STORE",
    materialization_store_path: "SCOS_PILOT_MATERIALIZATION_STATE",
    hvs_projects_root: "SCOS_PILOT_HVS_PROJECTS_ROOT",
    output_root: "SCOS_PILOT_OUTPUT_ROOT",
  };
  for (const [k, envKey] of Object.entries(SERVER_ROOT_KEYS)) {
    const v = process.env[envKey];
    if (v && v.length > 0) payload[k] = v;
  }
  const res = await invokeRenderReadiness(payload);
  return NextResponse.json(
    { ok: res.ok, state: res.state, error_code: res.error_code ?? null, detail: res.detail ?? null, checks: res.checks ?? [], projection: res.projection ?? null },
    { status: res.ok ? 200 : 422, headers: { "cache-control": "no-store" } },
  );
}
