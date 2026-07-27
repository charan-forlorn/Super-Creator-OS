/**
 * SCOS Cohort 10H — paid-pilot delivery package download (authorized only).
 *
 * Serves the sealed package zip back to the browser. The package path is
 * resolved SERVER-SIDE from the delivery record (never browser-supplied).
 * Only an authoritative DELIVERY_READY_FOR_MANUAL_HANDOFF (or
 * DELIVERY_PACKAGE_READY / DELIVERY_BACKUP_READY) package may be downloaded.
 * No absolute path, no repo path, no filesystem browsing.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { getDelivery } from "@/lib/paid-pilot-delivery-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ID_PATTERN = /^[a-z0-9_-]{2,96}$/;
const DOWNLOADABLE_STATES = new Set([
  "DELIVERY_PACKAGE_READY",
  "DELIVERY_BACKUP_READY",
  "DELIVERY_READY_FOR_MANUAL_HANDOFF",
]);

export async function GET(request: NextRequest) {
  const deliveryId = request.nextUrl.searchParams.get("deliveryId") ?? "";
  if (!ID_PATTERN.test(deliveryId)) {
    return NextResponse.json({ ok: false, error_code: "DELIVERY_ID_MALFORMED", detail: "invalid delivery id" }, { status: 400, headers: { "cache-control": "no-store" } });
  }

  const res = await getDelivery(deliveryId);
  if (!res.ok || !res.record) {
    return NextResponse.json({ ok: false, error_code: res.error_code ?? "DELIVERY_NOT_FOUND", detail: res.detail ?? null }, { status: 404, headers: { "cache-control": "no-store" } });
  }
  const record = res.record;
  if (!DOWNLOADABLE_STATES.has(record.state)) {
    return NextResponse.json({ ok: false, error_code: "DELIVERY_NOT_READY", detail: `state=${record.state}` }, { status: 409, headers: { "cache-control": "no-store" } });
  }

  // Resolve server-side package path from the trusted local store root.
  const root = process.env.SCOS_PAID_PILOT_PACKAGE_ROOT;
  if (!root || !root.length) {
    return NextResponse.json({ ok: false, error_code: "PACKAGE_ROOT_UNCONFIGURED", detail: "server package root unavailable" }, { status: 503, headers: { "cache-control": "no-store" } });
  }
  // Safe filename only (delivery_id derived, no traversal).
  const safeName = deliveryId.replace(/[^a-z0-9_-]/gi, "_") + ".zip";
  const pkgPath = path.join(root, safeName);
  try {
    const info = await stat(pkgPath);
    if (!info.isFile()) throw new Error("not a file");
    const bytes = await readFile(pkgPath);
    return new NextResponse(bytes, {
      status: 200,
      headers: {
        "content-type": "application/zip",
        "content-disposition": `attachment; filename="${safeName}"`,
        "cache-control": "no-store",
        "x-package-sha256": record.package_sha256 || "",
      },
    });
  } catch {
    return NextResponse.json({ ok: false, error_code: "PACKAGE_NOT_FOUND", detail: "package file unavailable" }, { status: 404, headers: { "cache-control": "no-store" } });
  }
}
