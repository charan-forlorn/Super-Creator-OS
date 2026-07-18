/**
 * Phase 2 — Brand Kit authoritative transport (GET + POST).
 *
 * Same-origin, local-first boundary. Mirrors app/api/project-preparation/route.ts:
 * strict ALLOWED_FIELDS allow-list, bounded body, unexpected-field rejection,
 * fail-closed persistence. Never writes memory/database.json, never executes a
 * subprocess, never reaches external network, never stores a browser path.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { BrandKitStore, brandKitStorePath, validateBrandKitInput, type BrandKitInput } from "@/lib/brand-kit-store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 8192;
const ALLOWED_FIELDS = new Set([
  "name",
  "colors",
  "fonts",
  "logo",
  "contact",
  "basic_cta",
]);

export async function GET(_request: NextRequest) {
  const store = new BrandKitStore(brandKitStorePath());
  const result = store.read();
  return NextResponse.json(
    {
      status: result.status,
      schema_version: 1,
      error_code: result.error_code,
      detail: result.detail,
      records: result.records,
    },
    { status: 200, headers: { "cache-control": "no-store", "content-type": "application/json" } },
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
  for (const key of Object.keys(body as Record<string, unknown>)) {
    if (!ALLOWED_FIELDS.has(key)) {
      return NextResponse.json(
        { ok: false, error_code: "REQUEST_UNEXPECTED_FIELD", detail: `unexpected field: ${key}` },
        { status: 400, headers: { "cache-control": "no-store" } },
      );
    }
  }

  const rec = body as Record<string, unknown>;
  const input: BrandKitInput = {
    name: typeof rec.name === "string" ? rec.name : "",
    colors: (rec.colors as BrandKitInput["colors"]) ?? {
      primary: "",
      secondary: "",
      accent: "",
      neutrals: [],
    },
    fonts: (rec.fonts as BrandKitInput["fonts"]) ?? { heading: "", body: "" },
    logo: (rec.logo as BrandKitInput["logo"]) ?? { asset_ref: "", kind: "local-ref" },
    contact: (rec.contact as BrandKitInput["contact"]) ?? { name: "", email: "", socials: [] },
    basic_cta: (rec.basic_cta as BrandKitInput["basic_cta"]) ?? { label: "", target: "" },
  };

  const validationErrors = validateBrandKitInput(input);
  if (validationErrors.length > 0) {
    return NextResponse.json(
      { ok: false, error_code: "VALIDATION_FAILED", detail: validationErrors.join("; ") },
      { status: 422, headers: { "cache-control": "no-store" } },
    );
  }

  const store = new BrandKitStore(brandKitStorePath());
  const result = store.upsert(input);
  if (!result.ok || !result.record) {
    const detail =
      result.error_code === "PERSISTENCE_WRITE_FAILED" ? "persistence unavailable" : result.detail;
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
