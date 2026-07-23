/**
 * SCOS Cohort 10H — browser-safe paid-pilot delivery client (pure fetch).
 *
 * This module contains NO node built-ins, NO child_process, NO filesystem
 * access. It is safe to bundle for the browser. Every business transition is a
 * same-origin fetch to the authoritative API; the Python bridge (spawn) lives
 * only in the server-side `paid-pilot-delivery-bridge.ts` imported by the route.
 *
 * The browser is projection + deliberate operator action only. No optimistic
 * state, no browser storage, no HVS call, no polling loop, no auto-retry.
 */

import type {
  BackupReceiptView,
  DeliveryProjectionView,
  DeliveryRecordView,
  DeliveryResponse,
  RightsChecklistEntryView,
} from "./paid-pilot-types";

async function post(op: string, body: Record<string, unknown>): Promise<DeliveryResponse> {
  try {
    const res = await fetch("/api/paid-pilot/delivery", {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ operation: op, ...body }),
    });
    const data = (await res.json()) as Record<string, unknown>;
    return {
      ok: Boolean(data.ok),
      error_code: (data.error_code as string | null) ?? null,
      detail: (data.detail as string | null) ?? null,
      record: (data.record as DeliveryRecordView | null) ?? null,
      package_sha256: (data.package_sha256 as string | null) ?? null,
      package_path: (data.package_path as string | null) ?? null,
      backup_receipt: (data.backup_receipt as BackupReceiptView | null) ?? null,
    };
  } catch (err: unknown) {
    return {
      ok: false,
      error_code: "REQUEST_FAILED",
      detail: err instanceof Error ? err.message : "unknown_error",
      record: null,
      package_sha256: null,
      package_path: null,
      backup_receipt: null,
    };
  }
}

export async function submitRightsReview(opts: {
  deliveryId: string;
  projectId: string;
  operatorId: string;
  reviewedAt: string;
  entries: RightsChecklistEntryView[];
  attestation?: string;
}): Promise<DeliveryResponse> {
  return post("rights-review", {
    delivery_id: opts.deliveryId,
    project_id: opts.projectId,
    operator_id: opts.operatorId,
    reviewed_at: opts.reviewedAt,
    entries: opts.entries,
    attestation: opts.attestation ?? "",
  });
}

export async function approveDelivery(opts: {
  deliveryId: string;
  operatorId: string;
  decidedAt: string;
  decision: "APPROVED_FOR_DELIVERY" | "REJECTED_REWORK_REQUIRED";
  sourceRenderAttemptId: string;
  artifactIdentity: string;
  artifactSha256: string;
  artifactSize: number;
  mediaProfile: string;
  qaRecordId: string;
  qaState: string;
  rightsRevision: string;
  rightsStatus: string;
  recordedAt: string;
}): Promise<DeliveryResponse> {
  return post("approve", {
    delivery_id: opts.deliveryId,
    operator_id: opts.operatorId,
    decided_at: opts.decidedAt,
    decision: opts.decision,
    source_render_attempt_id: opts.sourceRenderAttemptId,
    artifact_identity: opts.artifactIdentity,
    artifact_sha256: opts.artifactSha256,
    artifact_size: opts.artifactSize,
    media_profile: opts.mediaProfile,
    qa_record_id: opts.qaRecordId,
    qa_state: opts.qaState,
    rights_revision: opts.rightsRevision,
    rights_status: opts.rightsStatus,
    recorded_at: opts.recordedAt,
  });
}

export async function createDeliveryPackage(opts: {
  deliveryId: string;
  projectId: string;
  hvsProjectId: string;
  attemptId: string;
  profileId: string;
  qaReportId: string;
  artifactPath: string;
  operatorId: string;
  recordedAt: string;
  rightsRevision: string;
  rightsStatus: string;
  retentionClass: string;
}): Promise<DeliveryResponse> {
  return post("create-package", {
    delivery_id: opts.deliveryId,
    project_id: opts.projectId,
    hvs_project_id: opts.hvsProjectId,
    attempt_id: opts.attemptId,
    profile_id: opts.profileId,
    qa_report_id: opts.qaReportId,
    artifact_path: opts.artifactPath,
    operator_id: opts.operatorId,
    recorded_at: opts.recordedAt,
    rights_revision: opts.rightsRevision,
    rights_status: opts.rightsStatus,
    retention_class: opts.retentionClass,
  });
}

export async function markHandoffReady(deliveryId: string): Promise<DeliveryResponse> {
  return post("mark-handoff-ready", { delivery_id: deliveryId });
}

export async function getDelivery(deliveryId: string): Promise<DeliveryResponse> {
  try {
    const res = await fetch(`/api/paid-pilot/delivery?deliveryId=${encodeURIComponent(deliveryId)}`, { method: "GET", cache: "no-store" });
    const data = (await res.json()) as Record<string, unknown>;
    return {
      ok: Boolean(data.ok),
      error_code: (data.error_code as string | null) ?? null,
      detail: (data.detail as string | null) ?? null,
      record: (data.record as DeliveryRecordView | null) ?? null,
      package_sha256: (data.package_sha256 as string | null) ?? null,
      package_path: (data.package_path as string | null) ?? null,
      backup_receipt: (data.backup_receipt as BackupReceiptView | null) ?? null,
    };
  } catch (err: unknown) {
    return {
      ok: false,
      error_code: "REQUEST_FAILED",
      detail: err instanceof Error ? err.message : "unknown_error",
      record: null,
      package_sha256: null,
      package_path: null,
      backup_receipt: null,
    };
  }
}

export async function listDeliveries(): Promise<DeliveryResponse> {
  try {
    const res = await fetch("/api/paid-pilot/delivery", { method: "GET", cache: "no-store" });
    const data = (await res.json()) as Record<string, unknown>;
    return {
      ok: Boolean(data.ok),
      error_code: (data.error_code as string | null) ?? null,
      detail: (data.detail as string | null) ?? null,
      record: (data.record as DeliveryRecordView | null) ?? null,
      package_sha256: (data.package_sha256 as string | null) ?? null,
      package_path: (data.package_path as string | null) ?? null,
      backup_receipt: (data.backup_receipt as BackupReceiptView | null) ?? null,
    };
  } catch (err: unknown) {
    return {
      ok: false,
      error_code: "REQUEST_FAILED",
      detail: err instanceof Error ? err.message : "unknown_error",
      record: null,
      package_sha256: null,
      package_path: null,
      backup_receipt: null,
    };
  }
}

export function readDeliveryProjection(deliveryId: string): Promise<DeliveryProjectionView> {
  return getDelivery(deliveryId).then((res) => ({
    status: res.ok && res.record ? "AVAILABLE_WITH_DATA" : res.error_code === "DELIVERY_NOT_FOUND" ? "EMPTY" : "UNAVAILABLE",
    record: res.record,
  }));
}
