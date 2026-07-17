/**
 * Cohort 10D — read-only reconciliation of a materialization attempt (POST).
 *
 * Same-origin, local-first, READ-ONLY boundary. Classifies an existing
 * attempt's project presence at the destination through the Python
 * authority reached via the bridge. This route performs NO reconciliation
 * authority of its own: it validates the request, invokes exactly one
 * read-only bridge operation, and maps the classification. Never creates,
 * repairs, re-runs, renders, deletes, moves, or publishes. No HVS
 * mutation, no external network, no automatic retry, no browser-supplied
 * cwd/store/projects_root/command.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsMaterializationStore,
  buildReconcilePayload,
  serverResolvedScope,
} from "@/lib/hvs-materialization-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 2048;
const ATT_ID_PATTERN = /^[a-z0-9-]{4,48}$/;
const ALLOWED_FIELDS = new Set(["attemptId"]);

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
  if (!ATT_ID_PATTERN.test(attemptId)) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid attemptId" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const scope = serverResolvedScope();
  const store = new HvsMaterializationStore();
  const bridge = await store.invoke("reconcile", buildReconcilePayload({ attemptId, storePath: scope.storePath }));
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
      detail: null, // redacted
      classification: res.classification,
      attempt: res.attempt ?? null,
    },
    { status: res.ok ? 200 : 409, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
