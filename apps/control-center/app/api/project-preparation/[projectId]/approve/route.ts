/**
 * Cohort 10C — project-preparation approve exact revision (POST).
 *
 * Same-origin, local-first mutation boundary. Approves the exact project
 * revision through the authorative locked store (mirrors
 * scos/control_center/solo_project_preparation.py). Idempotent on
 * replay; rejects a stale revision (REVISION_CONFLICT); rejects an
 * unknown project; fail-closed on corrupt/unavailable store.
 *
 * NEVER writes memory/database.json, NEVER initializes HVS, NEVER starts a
 * render, NEVER reaches external network, NEVER executes a subprocess,
 * NEVER trusts a browser-supplied path.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { ProjectPreparationStore, projectPreparationStorePath } from "@/lib/project-preparation-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 2048;
const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  if (typeof projectId !== "string" || !SAFE_ID_PATTERN.test(projectId)) {
    return NextResponse.json(
      { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }

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

  let expectedRevision: number | null = null;
  if (raw.trim().length > 0) {
    try {
      const body = JSON.parse(raw) as Record<string, unknown>;
      const rv = body.expectedRevision;
      if (rv !== null && rv !== undefined) {
        if (typeof rv === "number" && Number.isInteger(rv) && rv >= 0) {
          expectedRevision = rv;
        } else {
          return NextResponse.json(
            { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid expectedRevision" },
            { status: 400, headers: { "cache-control": "no-store" } },
          );
        }
      }
    } catch {
      return NextResponse.json(
        { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid json" },
        { status: 400, headers: { "cache-control": "no-store" } },
      );
    }
  }

  const store = new ProjectPreparationStore(projectPreparationStorePath());
  const result = store.approve(projectId, expectedRevision);
  if (!result.ok) {
    // Mask internal detail on persistence failure so the absolute store
    // path / OS error text never reaches the browser (R4 security review).
    const detail =
      result.error_code === "PERSISTENCE_WRITE_FAILED"
        ? "persistence unavailable"
        : result.detail;
    return NextResponse.json(
      { ok: false, error_code: result.error_code, detail },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(
    { ok: true, error_code: null, detail: null, record: result.record },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
