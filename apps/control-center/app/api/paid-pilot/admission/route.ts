/** SCOS R2.1 — packet-admission API route (§6.A).

 *  Browser-safe, server-only. The browser submits ONLY: operation ("admit-packet")
 *  and expected_sha256 (operator seal, trusted). It may NOT submit any filesystem
 *  path. All roots and the packet path are resolved server-side from trusted
 *  environment variables. The route strips any path-shaped field defensively.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { invokeAdmission } from "@/lib/paid-pilot-admission-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX = 4096;
const OPS = new Set(["admit-packet"]);

// Browser must never control filesystem locations. Reject path-shaped keys.
const FORBIDDEN_KEYS = new Set([
  "packet_path", "approved_input_root", "admission_store_path", "audit_store_path",
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
  // Strip any path-shaped or unexpected field; only operation + expected_sha256 pass through.
  const expected = typeof body.expected_sha256 === "string" ? body.expected_sha256 : "";
  if (!expected) return safeError("EXPECTED_SHA_REQUIRED", "operator seal expected_sha256 is required");
  // Server resolves trusted roots from environment; the browser never supplies
  // these. They are injected only when present so the authority can operate on
  // task-owned state. (Matches this route's documented contract: packet path +
  // roots resolved server-side from trusted env.)
  const payload: Record<string, unknown> = { expected_sha256: expected };
  const SERVER_ROOT_KEYS: Record<string, string> = {
    packet_path: "SCOS_PILOT_PACKET_PATH",
    approved_input_root: "SCOS_PILOT_INPUT_ROOT",
    admission_store_path: "SCOS_PILOT_PACKET_ADMISSION_STORE",
    audit_store_path: "SCOS_PILOT_AUDIT_STORE",
  };
  for (const [k, envKey] of Object.entries(SERVER_ROOT_KEYS)) {
    const v = process.env[envKey];
    if (v && v.length > 0) payload[k] = v;
  }
  const res = await invokeAdmission(op, payload);
  return NextResponse.json(
    { ok: res.ok, error_code: res.error_code ?? null, detail: res.detail ?? null, gates: res.gates ?? [], assets: res.assets ?? [], projection: res.projection ?? null },
    { status: res.ok ? 200 : 422, headers: { "cache-control": "no-store" } },
  );
}
