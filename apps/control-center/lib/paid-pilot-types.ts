/**
 * SCOS Cohort 10H — browser-safe paid-pilot delivery types.
 *
 * These types are a pure serialization contract between the Next.js delivery
 * API (bridge to the Python authority) and the UI. They carry NO filesystem
 * paths, NO secrets, NO env vars. The browser receives only opaque ids,
 * safe filenames, hashes, and state.
 */

export type DeliveryState =
  | "DELIVERY_NOT_REQUESTED"
  | "DELIVERY_BLOCKED_QA_REQUIRED"
  | "DELIVERY_BLOCKED_QA_FAILED"
  | "DELIVERY_BLOCKED_RIGHTS_INCOMPLETE"
  | "DELIVERY_AWAITING_OPERATOR_APPROVAL"
  | "DELIVERY_REJECTED"
  | "DELIVERY_APPROVED"
  | "DELIVERY_PACKAGE_CREATING"
  | "DELIVERY_PACKAGE_READY"
  | "DELIVERY_PACKAGE_FAILED_CONFIRMED"
  | "DELIVERY_PACKAGE_OUTCOME_UNKNOWN"
  | "DELIVERY_PACKAGE_CORRUPT"
  | "DELIVERY_PACKAGE_INCOMPATIBLE"
  | "DELIVERY_BACKUP_READY"
  | "DELIVERY_READY_FOR_MANUAL_HANDOFF";

export type RightsState =
  | "RIGHTS_NOT_REVIEWED"
  | "RIGHTS_INCOMPLETE"
  | "RIGHTS_BLOCKED"
  | "RIGHTS_APPROVED";

export type OperatorDecision =
  | "APPROVAL_REQUIRED"
  | "APPROVED_FOR_DELIVERY"
  | "REJECTED_REWORK_REQUIRED";

export type RetentionClass =
  | "KEEP_UNTIL_OPERATOR_ARCHIVES"
  | "KEEP_FOR_PAID_PILOT_REVIEW"
  | "MANUAL_PURGE_REQUIRED";

export type DeliveryTruthState =
  | "EMPTY"
  | "AVAILABLE_WITH_DATA"
  | "UNAVAILABLE"
  | "CORRUPT"
  | "INCOMPATIBLE_SCHEMA"
  | "LOCKED";

export interface RightsChecklistEntryView {
  asset_kind: string;
  description: string;
  known_source: boolean;
  permitted: boolean;
  attribution_note: string;
}

export interface DeliveryRecordView {
  delivery_id: string;
  project_id: string;
  source_render_attempt_id: string;
  artifact_identity: string;
  artifact_sha256: string;
  artifact_size: number;
  media_profile: string;
  qa_record_id: string;
  qa_state: string;
  operator_id: string;
  operator_decision: OperatorDecision;
  rights_checklist_revision: string;
  rights_status: RightsState;
  package_revision: string;
  package_sha256: string;
  backup_receipt: BackupReceiptView | null;
  retention_class: RetentionClass;
  created_at: string;
  updated_at: string;
  state: DeliveryState;
}

export interface BackupReceiptView {
  backup_id: string;
  package_id: string;
  package_sha256: string;
  backup_sha256: string;
  created_at: string;
  protection_class: string;
}

export interface ReadinessCheckView {
  name: string;
  passed: boolean;
  reason_code: string;
  detail: string;
}

export interface DeliveryResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: DeliveryRecordView | null;
  package_sha256: string | null;
  package_path: string | null;
  backup_receipt: BackupReceiptView | null;
  // Read-only readiness projection fields (set only by the authoritative
  // Python 'readiness' op; the browser must never derive these itself).
  // Optional: other delivery ops do not populate them.
  readiness_state?: string | null;
  checks?: ReadinessCheckView[] | null;
  blocking_reasons?: string[] | null;
  backup_sha256?: string | null;
  audit_sha256?: string | null;
}

export interface DeliveryProjectionView {
  status: DeliveryTruthState;
  record: DeliveryRecordView | null;
}

export const ALLOWED_DELIVERY_STATES: DeliveryState[] = [
  "DELIVERY_NOT_REQUESTED",
  "DELIVERY_BLOCKED_QA_REQUIRED",
  "DELIVERY_BLOCKED_QA_FAILED",
  "DELIVERY_BLOCKED_RIGHTS_INCOMPLETE",
  "DELIVERY_AWAITING_OPERATOR_APPROVAL",
  "DELIVERY_REJECTED",
  "DELIVERY_APPROVED",
  "DELIVERY_PACKAGE_CREATING",
  "DELIVERY_PACKAGE_READY",
  "DELIVERY_PACKAGE_FAILED_CONFIRMED",
  "DELIVERY_PACKAGE_OUTCOME_UNKNOWN",
  "DELIVERY_PACKAGE_CORRUPT",
  "DELIVERY_PACKAGE_INCOMPATIBLE",
  "DELIVERY_BACKUP_READY",
  "DELIVERY_READY_FOR_MANUAL_HANDOFF",
];
