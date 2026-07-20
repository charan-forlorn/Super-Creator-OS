/**
 * Cohort 10E — read-only render reconciliation (POST).
 *
 * Same-origin, local-first read boundary. Invokes exactly one read-only
 * bridge reconciliation. The Python authority inspects the attempt record +
 * HVS project output at the server-resolved isolated root and classifies the
 * render as SUCCEEDED / FAILED_CONFIRMED / STILL_UNKNOWN. It NEVER starts
 * another render, repairs output, deletes artifacts, retries execution, or
 * consumes another capability. The browser supplies only the attempt id.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsRenderStore,
  buildReconcilePayload,
  serverResolvedScope,
} from "@/lib/hvs-render-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 4096;
const ID_PATTERN = /^[a-z0-9_-]{2,64}$/;
const ALLOWED_FIELDS = new Set([
  "attemptId",
]);

export async function POST(request: NextRequest) {
  let raw = "";
  try {
    const buf = await request.arrayBuffer();
    if (buf.byteLength > MAX_BODY_BYTES) {
      return NextResponse.json(
        { ok: false, error_code: "REQUEST_TOO_LARGE", detail: "payload exceeds limit" },
        { status: 413, headers: { "cache-control": "no-store" } },
      );
    }
    raw = Buffer.from(buf).toString("utf8");
  } catch {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_UNREADABLE", detail: "body unreadable" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid json" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  if (typeof body !== "object" || body === null) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "body not object" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  for (const key of Object.keys(body as Record<string, unknown>)) {
    if (!ALLOWED_FIELDS.has(key)) {
      return NextResponse.json(
        { ok: false, error_code: "REQUEST_UNEXPECTED_FIELD", detail: `unexpected field: ${key}` },
        { status: 400, headers: { "cache-control": "no-store" } },
      );
    }
  }

  const rec = body as Record<string, unknown>;
  const attemptId = typeof rec.attemptId === "string" ? rec.attemptId : "";
  if (!ID_PATTERN.test(attemptId)) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid attemptId" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const scope = serverResolvedScope();
  const store = new HvsRenderStore();
  const bridge = await store.invoke(
    "reconcile",
    buildReconcilePayload({ attemptId, storePath: scope.storePath }),
  );
  if (!bridge.ok || !bridge.response) {
    return NextResponse.json(
      { ok: false, error_code: bridge.error_code ?? "BRIDGE_FAILED", detail: "reconciliation unavailable" },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  const res = bridge.response;
  return NextResponse.json(
    {
      ok: res.ok,
      error_code: null,
      detail: null,
      classification: res.classification ?? null,
      attempt: res.attempt ?? null,
    },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
