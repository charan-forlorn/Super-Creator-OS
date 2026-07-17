/**
 * Cohort 10D — controlled HVS materialization execution (POST).
 *
 * Same-origin, local-first mutation boundary. Delegates the EXACT
 * authoritative orchestration (authorization eval, single-use capability,
 * in-flight containment, EXACTLY ONE real HVS mutation through the
 * adapter, identity gate, persistence) to the Python service reached via
 * the bridge. This route performs NO authority of its own: it validates
 * the request, invokes exactly one bridge operation, and maps the
 * structured response without inventing state. The browser supplies only
 * the reviewed intent + ids; the destination and plan hash are
 * server-resolved by the Python authority. No render, no FFmpeg/FFprobe/
 * Chromium/HyperFrames, no external network, no automatic retry, no
 * browser-supplied cwd/store/projects_root/command.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsMaterializationStore,
  buildExecutePayload,
  serverResolvedScope,
} from "@/lib/hvs-materialization-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 4096;
const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
const ID_PATTERN = /^[a-z0-9_-]{2,64}$/;
const ALLOWED_FIELDS = new Set([
  "projectId",
  "projectRevision",
  "authorizationId",
  "capabilityId",
  "attemptId",
  "operatorId",
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
  const projectId = typeof rec.projectId === "string" ? rec.projectId : "";
  const projectRevision = typeof rec.projectRevision === "number" && Number.isInteger(rec.projectRevision) && rec.projectRevision >= 0 ? rec.projectRevision : -1;
  const authorizationId = typeof rec.authorizationId === "string" ? rec.authorizationId : "";
  const capabilityId = typeof rec.capabilityId === "string" ? rec.capabilityId : "";
  const attemptId = typeof rec.attemptId === "string" ? rec.attemptId : "";
  const operatorId = typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator";

  if (!SAFE_ID_PATTERN.test(projectId)) {
    return NextResponse.json(
      { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }
  if (projectRevision < 0) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid projectRevision" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  if (!ID_PATTERN.test(capabilityId) || !ID_PATTERN.test(attemptId) || !ID_PATTERN.test(authorizationId)) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid id" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  // Invoke exactly ONE bridge operation. All authority lives in Python.
  const scope = serverResolvedScope();
  const store = new HvsMaterializationStore();
  const bridge = await store.invoke(
    "execute",
    buildExecutePayload({
      projectId,
      projectRevision,
      authorizationId,
      capabilityId,
      attemptId,
      operatorId,
      storePath: scope.storePath,
      projectsRoot: scope.projectsRoot,
    }),
  );
  if (!bridge.ok || !bridge.response) {
    const detail = bridge.error_code === "BRIDGE_TIMEOUT" ? "bridge timeout"
      : bridge.error_code === "BRIDGE_OUTPUT_OVERSIZED" ? "bridge output too large"
      : "execution unavailable";
    return NextResponse.json(
      {
        ok: false,
        error_code: bridge.error_code ?? "BRIDGE_FAILED",
        detail,
        result: {
          ok: false,
          state: "MATERIALIZATION_FAILED_CONFIRMED",
          attempt_id: attemptId,
          authorization_id: authorizationId,
          capability_id: capabilityId,
          hvs_calls: 0,
          outcome: "rejected",
          error_code: bridge.error_code ?? "BRIDGE_FAILED",
          error_detail: null,
          persisted_result: null,
        },
      },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }

  // The Python CLI returns a FLAT authoritative envelope
  // ({ok, state, attempt_id, ..., hvs_calls, ...}) — there is no `result`
  // wrapper. Map it into the route's `result` shape. The transport verdict
  // is `bridge.ok` (exit 0 + structured JSON); the authority verdict lives
  // inside the envelope's own `ok`/`error_code` and is surfaced verbatim.
  const flat = bridge.response as unknown as Record<string, unknown> | null;
  const shaped = {
    ok: Boolean(flat?.ok ?? false),
    state: (flat?.state as string) ?? "MATERIALIZATION_FAILED_CONFIRMED",
    attempt_id: (flat?.attempt_id as string) ?? attemptId,
    authorization_id: (flat?.authorization_id as string) ?? authorizationId,
    capability_id: (flat?.capability_id as string) ?? capabilityId,
    hvs_calls: Number(flat?.hvs_calls ?? 0),
    outcome: (flat?.outcome as string | null) ?? null,
    error_code: (flat?.error_code as string | null) ?? null,
    error_detail: null, // never leak raw detail/paths to browser
    persisted_result: (flat?.persisted_result as Record<string, unknown> | null) ?? null,
  };

  return NextResponse.json(
    {
      ok: bridge.ok,
      error_code: shaped.error_code,
      detail: null, // redacted
      result: shaped,
    },
    { status: bridge.ok ? 200 : 409, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
