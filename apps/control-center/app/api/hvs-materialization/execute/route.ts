/**
 * Cohort 10D — controlled HVS materialization execution (POST).
 *
 * Same-origin, local-first mutation boundary. Runs the authoritative
 * materialization orchestration (authorization eval, single-use capability,
 * in-flight containment, EXACTLY ONE HVS mutation through the controlled
 * local boundary, identity gate, persistence). The browser supplies only the
 * reviewed intent + ids; the destination and plan hash are server-resolved.
 * No render, no FFmpeg/FFprobe/Chromium/HyperFrames, no external network, no
 * automatic retry.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  HvsMaterializationStore,
  hvsMaterializationStorePath,
  type AttemptRecord,
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

  // Load the authoritative authorization issued by the authorize route.
  const store = new HvsMaterializationStore(hvsMaterializationStorePath());
  const authorization = store.getAuthorization(authorizationId);

  const result = store.executeMaterialization({
    projectId,
    projectRevision,
    normalized: {
      project_title: "",
      client_or_brand: "",
      project_purpose: "",
      normalized_brief_summary: "",
      target_duration_seconds: 0,
      output_profiles: [],
      planned_rendition_count: 0,
      operator_notes: "",
    },
    authorization,
    capabilityId,
    attemptId,
    operatorId,
  });

  if (!result.ok || !result.result) {
    const detail = result.error_code === "PERSISTENCE_WRITE_FAILED" ? "persistence unavailable" : result.detail;
    // Still return the structured result so clients can render the contained
    // outcome (e.g. CAPABILITY_CONSUMED / INFLIGHT_ATTEMPT) without guessing.
    const shaped = result.result
      ? {
          ok: result.result.ok,
          state: result.result.state,
          attempt_id: result.result.attemptId,
          authorization_id: result.result.authorizationId,
          capability_id: result.result.capabilityId,
          hvs_calls: result.result.hvsCalls,
          outcome: result.result.outcome,
          error_code: result.result.errorCode,
          error_detail: result.result.errorDetail,
          persisted_result: null,
        }
      : {
          ok: false,
          state: "MATERIALIZATION_FAILED_CONFIRMED",
          attempt_id: attemptId,
          authorization_id: authorizationId,
          capability_id: capabilityId,
          hvs_calls: 0,
          outcome: "rejected",
          error_code: result.error_code,
          error_detail: detail,
          persisted_result: null,
        };
    return NextResponse.json(
      { ok: false, error_code: result.error_code, detail, result: shaped },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(
    {
      ok: result.result.ok,
      error_code: result.result.errorCode,
      detail: result.result.errorDetail,
      result: {
        ok: result.result.ok,
        state: result.result.state,
        attempt_id: result.result.attemptId,
        authorization_id: result.result.authorizationId,
        capability_id: result.result.capabilityId,
        hvs_calls: result.result.hvsCalls,
        outcome: result.result.outcome,
        error_code: result.result.errorCode,
        error_detail: result.result.errorDetail,
        persisted_result: (result.record as AttemptRecord | null)?.persisted_result ?? null,
      },
    },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
