/** SCOS R2.2 — canonical paid-pilot project creation API route (§6.E/§6.F bridge).

 *  Browser-safe, server-only. The browser submits ONLY: operation
 *  ("create-canonical-project") and an idempotency key (server-generated in the
 *  wizard, never a filesystem path). All roots, stores, the packet path and the
 *  contracts directory are resolved server-side from trusted environment
 *  variables. The route strips any path-shaped field defensively.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { invokeCreateCanonical } from "@/lib/paid-pilot-create-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX = 4096;
const OPS = new Set(["create-canonical-project"]);

// Browser must never control filesystem locations. Reject path-shaped keys.
const FORBIDDEN_KEYS = new Set([
  "packet_path", "approved_input_root", "admission_store_path", "identity_store_path",
  "materialization_store_path", "hvs_projects_root", "output_root", "contracts_dir",
  "store_path", "evidence_base", "runtime_base", "file_path", "asset_path",
]);

function safeError(code: string, detail: string, status = 400) {
  return NextResponse.json({ ok: false, error_code: code, detail, projection: null }, { status, headers: { "cache-control": "no-store" } });
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
  const op = typeof body.operation === "string" ? body.operation : "";
  if (!OPS.has(op)) return safeError("UNKNOWN_OPERATION", op);

  // Defensive strip of any path-shaped or unexpected field.
  for (const k of Object.keys(body)) {
    if (FORBIDDEN_KEYS.has(k)) return safeError("FORBIDDEN_FIELD", `browser may not supply ${k}`);
  }

  const idempotency_key = typeof body.idempotency_key === "string" && body.idempotency_key.length > 0
    ? body.idempotency_key
    : "";
  if (!idempotency_key) {
    return safeError("IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required");
  }
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(idempotency_key)) {
    return safeError("IDEMPOTENCY_KEY_INVALID", "idempotency key contains unsafe characters");
  }

  // Server resolves trusted roots from environment; the browser never supplies these.
  const payload: Record<string, unknown> = { idempotency_key };
  const SERVER_ROOT_KEYS: Record<string, string> = {
    packet_path: "SCOS_PILOT_PACKET_PATH",
    approved_input_root: "SCOS_PILOT_INPUT_ROOT",
    admission_store_path: "SCOS_PILOT_PACKET_ADMISSION_STORE",
    identity_store_path: "SCOS_PILOT_IDENTITY_STORE",
    materialization_store_path: "SCOS_PILOT_MATERIALIZATION_STATE",
    hvs_projects_root: "SCOS_PILOT_HVS_PROJECTS_ROOT",
    output_root: "SCOS_PILOT_OUTPUT_ROOT",
    contracts_dir: "SCOS_PILOT_CONTRACTS_DIR",
  };
  for (const [k, envKey] of Object.entries(SERVER_ROOT_KEYS)) {
    const v = process.env[envKey];
    if (v && v.length > 0) payload[k] = v;
  }
  const res = await invokeCreateCanonical(op, payload);
  return NextResponse.json(
    {
      ok: res.ok,
      error_code: res.error_code ?? null,
      detail: res.detail ?? null,
      canonical_internal_project_id: res.canonical_internal_project_id ?? null,
      pilot_safe_id: res.pilot_safe_id ?? null,
      project_safe_id: res.project_safe_id ?? null,
      external_project_ref: res.external_project_ref ?? null,
      admission_packet_sha256: res.admission_packet_sha256 ?? null,
      replay: res.replay ?? null,
      materialization: res.materialization ?? null,
      next_safe_action: res.next_safe_action ?? null,
    },
    { status: res.ok ? 200 : 422, headers: { "cache-control": "no-store" } },
  );
}
