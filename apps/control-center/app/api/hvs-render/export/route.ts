/**
 * Phase 2 — Export Package endpoint (controlled stub).
 *
 * A real Python export backend does NOT exist yet (the HVS adapter allowlist
 * forbids the export operation). This route is fail-closed:
 *  - without SCOS_EXPORT_STUB_ENABLED it refuses every request (EXPORT_NOT_READY),
 *    so the UI export control stays inert and never shows a fabricated success;
 *  - with SCOS_EXPORT_STUB_ENABLED=1 it returns a deterministic package envelope
 *    (data: URL + sha256 placeholder) for the Golden Project E2E test-double only.
 *
 * No subprocess, no network, no mutation, no write to memory/database.json.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { createHash } from "node:crypto";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const STUB_ENABLED = process.env.SCOS_EXPORT_STUB_ENABLED === "1";

export async function POST(request: NextRequest) {
  if (!STUB_ENABLED) {
    return NextResponse.json(
      {
        ok: false,
        error_code: "EXPORT_NOT_READY",
        detail: "Export backend not yet available — export control is inert by design.",
      },
      { status: 409, headers: { "cache-control": "no-store" } },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid json" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  const attemptId = (body as Record<string, unknown>)?.attemptId;
  if (typeof attemptId !== "string" || !/^[a-z0-9_-]{2,64}$/.test(attemptId)) {
    return NextResponse.json(
      { ok: false, error_code: "ATTEMPT_ID_MALFORMED", detail: "invalid attemptId" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  const manifest = JSON.stringify({ attemptId, package: "golden-project-export", format: "json" });
  const encoded = Buffer.from(manifest, "utf8").toString("base64");
  const downloadUrl = `data:application/json;base64,${encoded}`;
  const sha256 = createHash("sha256").update(manifest).digest("hex");

  return NextResponse.json(
    { ok: true, error_code: null, detail: null, download_url: downloadUrl, sha256 },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
  );
}
