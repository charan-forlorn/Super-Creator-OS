/**
 * Cohort 10C — project-preparation authoritative transport.
 *
 * Same-origin, local-first boundary. The browser is NEVER the authority
 * (Cohort 10C §3): all truth after creation/transition is derived from
 * the authorative locked store
 * (memory/runtime/control-center/project-preparation-v1.json), mirroring the
 * Python service scos/control_center/solo_project_preparation.py 1:1.
 *
 *  GET  -> read truth state (AVAILABLE_WITH_DATA | EMPTY | UNAVAILABLE
 *          | CORRUPT | INCOMPATIBLE_SCHEMA). read-only, no write.
 *  POST -> create a validated project draft (persists authorative record).
 *
 * NEVER writes memory/database.json, NEVER initializes HVS, NEVER starts a
 * render, NEVER reaches external network, NEVER executes a subprocess,
 * NEVER stores a browser-supplied path or secret.
 */

import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  ProjectPreparationStore,
  validateDraftInput,
} from "@/lib/project-preparation-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const STORE_RELATIVE_PATH =
  ".." + "/" + ".." + "/" + ".." + "/" + "memory" + "/" + "runtime" + "/" + "control-center" + "/" + "project-preparation-v1.json";

function storePath(): string {
  const base = dirname(fileURLToPath(import.meta.url));
  return base + "/" + STORE_RELATIVE_PATH;
}

const MAX_BODY_BYTES = 8192;
const ALLOWED_FIELDS = new Set([
  "projectTitle",
  "clientOrBrand",
  "projectPurpose",
  "contentBrief",
  "targetDurationSeconds",
  "outputProfiles",
  "operatorNotes",
]);

export async function GET(_request: NextRequest) {
  const store = new ProjectPreparationStore(storePath());
  const result = store.read();
  return NextResponse.json(
    {
      status: result.status,
      schema_version: 1,
      error_code: result.error_code,
      detail: result.detail,
      records: result.records,
    },
    {
      status: 200,
      headers: { "cache-control": "no-store", "content-type": "application/json" },
    },
  );
}

export async function POST(request: NextRequest) {
  let raw: string;
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
  // Reject unexpected fields (no arbitrary path / secret / foreign keys).
  for (const key of Object.keys(body as Record<string, unknown>)) {
    if (!ALLOWED_FIELDS.has(key)) {
      return NextResponse.json(
        { ok: false, error_code: "REQUEST_UNEXPECTED_FIELD", detail: `unexpected field: ${key}` },
        { status: 400, headers: { "cache-control": "no-store" } },
      );
    }
  }

  const record = body as Record<string, unknown>;
  const input = {
    projectTitle: typeof record.projectTitle === "string" ? record.projectTitle : "",
    clientOrBrand: typeof record.clientOrBrand === "string" ? record.clientOrBrand : "",
    projectPurpose: typeof record.projectPurpose === "string" ? record.projectPurpose : "",
    contentBrief: typeof record.contentBrief === "string" ? record.contentBrief : "",
    targetDurationSeconds: typeof record.targetDurationSeconds === "number" ? record.targetDurationSeconds : 0,
    outputProfiles: Array.isArray(record.outputProfiles) ? record.outputProfiles.map((p) => String(p)) : [],
    operatorNotes: typeof record.operatorNotes === "string" ? record.operatorNotes : "",
  };

  const validationErrors = validateDraftInput(input);
  if (validationErrors.length > 0) {
    return NextResponse.json(
      { ok: false, error_code: "VALIDATION_FAILED", detail: validationErrors.join("; ") },
      { status: 422, headers: { "cache-control": "no-store" } },
    );
  }

  const store = new ProjectPreparationStore(storePath());
  const result = store.createDraft(input);
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
