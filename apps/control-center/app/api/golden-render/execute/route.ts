/**
 * Cohort 10G — golden render execute (POST).
 *
 * Same-origin, local-first mutation boundary. Delegates the EXACT
 * authoritative orchestration (operator authorization gate, single real HVS
 * render via the render-pack boundary, media QA, persistence) to the Python
 * service reached via the bridge. This route performs NO authority of its
 * own: it validates the request, invokes exactly one bridge "execute"
 * operation, and maps the structured response without inventing state. The
 * browser supplies only the reviewed intent + ids; the HVS repo root and
 * store path are server-resolved. No FFmpeg/FFprobe/Chromium/HyperFrames from
 * the browser, no external network, no automatic retry, no browser-supplied
 * cwd/store/projects_root/command.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  GoldenRenderStore,
} from "@/lib/golden-render-store";
import {
  buildExecutePayload,
  serverResolvedScope,
} from "@/lib/golden-render-contract";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 4096;
const PROJECT_ID_PATTERN = /^coh10g_[vsl]$/;
const ID_PATTERN = /^[a-z0-9_-]{2,64}$/;
const PROFILE_PATTERN = /^(vertical_9_16|square_1_1|landscape_16_9)$/;
const ALLOWED_FIELDS = new Set([
  "projectId",
  "hvsProjectId",
  "profileId",
  "authorizationId",
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
  const hvsProjectId = typeof rec.hvsProjectId === "string" ? rec.hvsProjectId : "";
  const profileId = typeof rec.profileId === "string" ? rec.profileId : "";
  const authorizationId = typeof rec.authorizationId === "string" ? rec.authorizationId : "";
  const operatorId = typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator";

  if (!PROJECT_ID_PATTERN.test(projectId)) {
    return NextResponse.json(
      { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }
  if (!ID_PATTERN.test(hvsProjectId) || !PROFILE_PATTERN.test(profileId) || !ID_PATTERN.test(authorizationId)) {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid id" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const scope = serverResolvedScope();
  const store = new GoldenRenderStore();
  const bridge = await store.invoke(
    "execute",
    buildExecutePayload({
      projectId,
      hvsProjectId,
      profileId: profileId as "vertical_9_16" | "square_1_1" | "landscape_16_9",
      authorizationId,
      operatorId,
      storePath: scope.storePath,
    }),
  );
  if (!bridge.ok || !bridge.response) {
    return NextResponse.json(
      { ok: false, error_code: bridge.error_code ?? "BRIDGE_FAILED", detail: "execution unavailable" },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }

  const flat = bridge.response as unknown as Record<string, unknown>;
  return NextResponse.json(
    {
      ok: bridge.ok,
      error_code: flat.error_code ?? null,
      result: {
        state: (flat.state as string) ?? "RENDER_FAILED_CONFIRMED",
        attempt_id: (flat.attempt_id as string) ?? null,
        artifact_id: (flat.artifact_id as string) ?? null,
        artifact_checksum: (flat.artifact_checksum as string) ?? null,
        render_calls: Number(flat.render_calls ?? 0),
        hvs_calls: Number(flat.hvs_calls ?? 0),
        qa_overall_state: (flat.qa_overall_state as string | null) ?? null,
        qa_report_id: (flat.qa_report_id as string | null) ?? null,
        qa_failure_codes: Array.isArray(flat.qa_failure_codes) ? (flat.qa_failure_codes as string[]) : [],
        attempt: (flat.attempt as Record<string, unknown> | null) ?? null,
        qa_report: (flat.qa_report as Record<string, unknown> | null) ?? null,
      },
    },
    { status: bridge.ok ? 200 : 409, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
