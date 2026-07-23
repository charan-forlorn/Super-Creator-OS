/**
 * SCOS Cohort 10H — paid-pilot delivery API (browser-safe mutation bridge).
 *
 * Same-origin local-first boundary. All validation is bounded; all
 * persistence lives in the Python authority reached through the bridge. The
 * browser supplies only reviewed intent + opaque ids. No filesystem paths,
 * no secrets, no HVS calls, no network.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  approveDelivery,
  createDeliveryPackage,
  getDelivery,
  listDeliveries,
  markHandoffReady,
  submitRightsReview,
} from "@/lib/paid-pilot-delivery-bridge";
import type { RightsChecklistEntryView } from "@/lib/paid-pilot-types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_BODY_BYTES = 8192;
const ID_PATTERN = /^[a-z0-9_-]{2,96}$/;

export async function GET(request: NextRequest) {
  const deliveryId = request.nextUrl.searchParams.get("deliveryId") ?? "";
  const res = deliveryId ? await getDelivery(deliveryId) : await listDeliveries();
  return NextResponse.json(res, {
    status: res.ok ? 200 : res.error_code === "DELIVERY_NOT_FOUND" ? 404 : 409,
    headers: { "cache-control": "no-store" },
  });
}

export async function POST(request: NextRequest) {
  let raw = "";
  try {
    const buf = await request.arrayBuffer();
    if (buf.byteLength > MAX_BODY_BYTES) {
      return NextResponse.json({ ok: false, error_code: "REQUEST_TOO_LARGE", detail: "payload exceeds limit" }, { status: 413, headers: { "cache-control": "no-store" } });
    }
    raw = Buffer.from(buf).toString("utf8");
  } catch {
    return NextResponse.json({ ok: false, error_code: "REQUEST_UNREADABLE", detail: "body unreadable" }, { status: 400, headers: { "cache-control": "no-store" } });
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "invalid json" }, { status: 400, headers: { "cache-control": "no-store" } });
  }
  if (typeof body !== "object" || body === null) {
    return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "body not object" }, { status: 400, headers: { "cache-control": "no-store" } });
  }
  const rec = body as Record<string, unknown>;
  const op = typeof rec.operation === "string" ? rec.operation : "";

  if (op === "rights-review") {
    const projectId = typeof rec.projectId === "string" ? rec.projectId : "";
    const operatorId = typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator";
    const reviewedAt = typeof rec.reviewedAt === "string" ? rec.reviewedAt : "";
    const entriesRaw = Array.isArray(rec.entries) ? rec.entries : [];
    const entries: RightsChecklistEntryView[] = entriesRaw
      .filter((e): e is Record<string, unknown> => typeof e === "object" && e !== null)
      .map((e) => ({
        asset_kind: String(e.asset_kind ?? ""),
        description: String(e.description ?? ""),
        known_source: Boolean(e.known_source),
        permitted: Boolean(e.permitted),
        attribution_note: String(e.attribution_note ?? ""),
      }));
    if (!ID_PATTERN.test(projectId) || !reviewedAt) {
      return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "missing project/review identity" }, { status: 400, headers: { "cache-control": "no-store" } });
    }
    const deliveryId = typeof rec.deliveryId === "string" && ID_PATTERN.test(rec.deliveryId) ? rec.deliveryId : `scos-hvs-pp-delivery-${projectId}`;
    const res = await submitRightsReview({ deliveryId, projectId, operatorId, reviewedAt, entries, attestation: typeof rec.attestation === "string" ? rec.attestation : "" });
    return NextResponse.json(res, { status: res.ok ? 200 : 409, headers: { "cache-control": "no-store" } });
  }

  if (op === "approve") {
    const deliveryId = typeof rec.deliveryId === "string" ? rec.deliveryId : "";
    const decision = rec.decision === "APPROVED_FOR_DELIVERY" || rec.decision === "REJECTED_REWORK_REQUIRED" ? rec.decision : "";
    if (!ID_PATTERN.test(deliveryId) || !decision) {
      return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "missing delivery/decision" }, { status: 400, headers: { "cache-control": "no-store" } });
    }
    const res = await approveDelivery({
      deliveryId,
      operatorId: typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator",
      decidedAt: typeof rec.decidedAt === "string" ? rec.decidedAt : "",
      decision,
      sourceRenderAttemptId: String(rec.sourceRenderAttemptId ?? ""),
      artifactIdentity: String(rec.artifactIdentity ?? ""),
      artifactSha256: String(rec.artifactSha256 ?? ""),
      artifactSize: Number(rec.artifactSize ?? 0),
      mediaProfile: String(rec.mediaProfile ?? ""),
      qaRecordId: String(rec.qaRecordId ?? ""),
      qaState: String(rec.qaState ?? ""),
      rightsRevision: String(rec.rightsRevision ?? ""),
      rightsStatus: String(rec.rightsStatus ?? ""),
      recordedAt: typeof rec.recordedAt === "string" ? rec.recordedAt : "",
    });
    return NextResponse.json(res, { status: res.ok ? 200 : 409, headers: { "cache-control": "no-store" } });
  }

  if (op === "create-package") {
    const deliveryId = typeof rec.deliveryId === "string" ? rec.deliveryId : "";
    if (!ID_PATTERN.test(deliveryId)) {
      return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "missing delivery id" }, { status: 400, headers: { "cache-control": "no-store" } });
    }
    const res = await createDeliveryPackage({
      deliveryId,
      projectId: String(rec.projectId ?? ""),
      hvsProjectId: String(rec.hvsProjectId ?? ""),
      attemptId: String(rec.attemptId ?? ""),
      profileId: String(rec.profileId ?? ""),
      qaReportId: String(rec.qaReportId ?? ""),
      artifactPath: String(rec.artifactPath ?? ""),
      operatorId: typeof rec.operatorId === "string" ? rec.operatorId : "local-solo-operator",
      recordedAt: typeof rec.recordedAt === "string" ? rec.recordedAt : "",
      rightsRevision: String(rec.rightsRevision ?? ""),
      rightsStatus: String(rec.rightsStatus ?? ""),
      retentionClass: typeof rec.retentionClass === "string" ? rec.retentionClass : "MANUAL_PURGE_REQUIRED",
    });
    return NextResponse.json(res, { status: res.ok ? 200 : 409, headers: { "cache-control": "no-store" } });
  }

  if (op === "mark-handoff-ready") {
    const deliveryId = typeof rec.deliveryId === "string" ? rec.deliveryId : "";
    if (!ID_PATTERN.test(deliveryId)) {
      return NextResponse.json({ ok: false, error_code: "REQUEST_MALFORMED", detail: "missing delivery id" }, { status: 400, headers: { "cache-control": "no-store" } });
    }
    const res = await markHandoffReady(deliveryId);
    return NextResponse.json(res, { status: res.ok ? 200 : 409, headers: { "cache-control": "no-store" } });
  }

  return NextResponse.json({ ok: false, error_code: "UNKNOWN_OPERATION", detail: op }, { status: 400, headers: { "cache-control": "no-store" } });
}
