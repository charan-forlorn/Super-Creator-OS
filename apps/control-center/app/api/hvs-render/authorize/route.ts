/**
 * Cohort 10E — HVS render authorization request (POST).
 *
 * Same-origin, local-first mutation boundary. Issues an immutable, bound
 * authorization ONLY when the operator explicitly confirms. The authoritative
 * decision, plan hash, capability, and persistence all live in the Python
 * service reached through the bridge. The browser supplies only the reviewed
 * intent + ids; the destination and plan hash are server-resolved. No
 * HVS call, no render, no external network.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsRenderStore,
  buildAuthorizePayload,
  serverResolvedScope,
} from "@/lib/hvs-render-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 4096;
const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
const ID_PATTERN = /^[a-z0-9_-]{2,64}$/;
const ALLOWED_FIELDS = new Set([
  "projectId",
  "projectRevision",
  "confirmed",
  "operatorId",
  "materializationAttemptId",
  "materializationPlanHash",
  "renderProfileId",
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
  const confirmed = rec.confirmed === true;
  const materializationAttemptId = typeof rec.materializationAttemptId === "string" ? rec.materializationAttemptId : "";
  const materializationPlanHash = typeof rec.materializationPlanHash === "string" ? rec.materializationPlanHash : "";
  const renderProfileId = typeof rec.renderProfileId === "string" && /^[a-z0-9_]{2,32}$/.test(rec.renderProfileId) ? rec.renderProfileId : "vertical";

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
  if (!ID_PATTERN.test(materializationAttemptId) || materializationPlanHash.length < 8) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "missing materialization identity" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  const operatorId = typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator";

  const scope = serverResolvedScope();
  const store = new HvsRenderStore();
  const bridge = await store.invoke(
    "authorize",
    buildAuthorizePayload({
      projectId,
      projectRevision,
      confirmed,
      operatorId,
      materializationAttemptId,
      materializationPlanHash,
      renderProfileId,
      storePath: scope.storePath,
    }),
  );
  if (!bridge.ok || !bridge.response) {
    return NextResponse.json(
      { ok: false, error_code: bridge.error_code ?? "BRIDGE_FAILED", detail: "authorization unavailable" },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  const res = bridge.response;
  if (!res.ok || !res.authorization) {
    return NextResponse.json(
      { ok: false, error_code: res.error_code ?? "REQUEST_REJECTED", detail: res.detail ?? null, decision: res.decision ?? undefined },
      { status: confirmed ? 409 : 422, headers: { "cache-control": "no-store" } },
    );
  }
  const auth = res.authorization;
  return NextResponse.json(
    {
      ok: true,
      error_code: null,
      detail: null,
      decision: res.decision,
      authorization: {
        authorization_id: auth.authorization_id,
        project_id: auth.project_id,
        project_revision: auth.project_revision,
        operation: auth.operation,
        materialization_attempt_id: auth.materialization_attempt_id,
        render_profile_id: auth.render_profile_id,
        render_plan_hash: auth.render_plan_hash,
        output_root_identity: auth.output_root_identity,
        decision: auth.decision,
      },
    },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
