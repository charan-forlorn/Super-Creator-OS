/**
 * SCOS Cohort 10I — paid-pilot readiness projection API route.
 *
 * Browser-safe, read-only endpoint. It does NOT derive readiness itself:
 * it delegates to the authoritative Python paid-pilot readiness authority
 * (via the server-only bridge) so the Python authority remains the single
 * source of truth (master §10). The browser never writes or overstates
 * readiness state.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getReadiness } from "@/lib/paid-pilot-delivery-bridge";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ID_PATTERN = /^[a-z0-9_-]{2,96}$/;

export async function GET(request: NextRequest) {
  const deliveryId = request.nextUrl.searchParams.get("deliveryId") ?? "";
  if (!ID_PATTERN.test(deliveryId)) {
    return NextResponse.json(
      { ok: false, error_code: "DELIVERY_ID_MALFORMED", detail: "invalid delivery id" },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  // Delegate to the authoritative Python readiness projection. If the authority
  // returns no record, report NOT_READY with a browser-safe reason.
  const res = await getReadiness(deliveryId);
  const body = res as unknown as Record<string, unknown>;
  if (!res.ok || !body.record) {
    return NextResponse.json(
      {
        ok: true,
        state: "NOT_READY",
        delivery_id: deliveryId,
        checks: [],
        blocking_reasons: ["NO_DELIVERY_RECORD"],
        package_sha256: null,
        backup_sha256: null,
        audit_sha256: null,
      },
      { status: 200, headers: { "cache-control": "no-store" } },
    );
  }

  const projection = body as {
    state: string;
    delivery_id: string;
    checks?: Array<{ name: string; passed: boolean; reason_code: string; detail: string }>;
    blocking_reasons?: string[];
    package_sha256?: string;
    backup_sha256?: string;
    audit_sha256?: string;
  };

  return NextResponse.json(
    {
      ok: true,
      state: projection.state,
      delivery_id: projection.delivery_id,
      // Browser-safe: omit raw detail for failed checks only when it could
      // leak paths; the authority already redacts (no absolute paths/secrets).
      checks: projection.checks ?? [],
      blocking_reasons: projection.blocking_reasons ?? [],
      package_sha256: projection.package_sha256 || null,
      backup_sha256: projection.backup_sha256 || null,
      audit_sha256: projection.audit_sha256 || null,
    },
    { status: 200, headers: { "cache-control": "no-store" } },
  );
}
