/**
 * Cohort 9A — Truthful read-only Control Center snapshot transport.
 *
 * GET /api/control-center-snapshot
 *
 * This route is the local-only, read-only transport boundary. It:
 *  - performs a single fs.readFileSync on a committed JSON snapshot artifact
 *    (produced hermetically by scos/control_center/control_center_snapshot.py);
 *  - returns the snapshot with source_mode preserved;
 *  - NEVER writes files, NEVER spawns a subprocess, NEVER calls Python,
 *    NEVER opens a socket, and NEVER reaches external network.
 *
 * No mutation method (POST/PUT/PATCH/DELETE) exists. The only capability is
 * reading an already-generated local artifact.
 */

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Local-only: this route must not be statically optimized away into a build
// artifact that could be cached by an external CDN, and must run per-request
// against the committed artifact.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Anchor to this module's location, not process.cwd() — `next start`
// runs with cwd = the app directory, so cwd-relative paths break.
const ARTIFACT_RELATIVE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "data",
  "control-center-snapshot.json",
);

export async function GET(_request: NextRequest) {
  try {
    const raw = readFileSync(ARTIFACT_RELATIVE_PATH, "utf8");
    const snapshot = JSON.parse(raw) as Record<string, unknown>;
    // Defensive: never serve anything that claims a non-read-only source mode.
    if (snapshot.source_mode !== "LIVE_LOCAL_READ_ONLY") {
      return NextResponse.json(
        { error: "unexpected_source_mode", source_mode: snapshot.source_mode },
        { status: 500 },
      );
    }
    return NextResponse.json(snapshot, {
      status: 200,
      headers: {
        "cache-control": "no-store",
        "content-type": "application/json",
      },
    });
  } catch {
    // Truthful failure envelope — no internal detail leaked.
    return NextResponse.json(
      {
        error: "snapshot_unavailable",
        source_mode: "LIVE_LOCAL_READ_ONLY",
        health: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        queue_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        approval_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        project_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        recent_activity: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_FAILED", observed_at: new Date().toISOString() },
        degradation_reasons: ["READ_FAILED"],
      },
      { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
    );
  }
}
