/**
 * Stage 6.3 static types mirroring scos/control_center/state_models.py and
 * state_snapshot.py. No runtime behavior here -- these are display-only
 * shapes for the static Stage 6.3 mock panels. Nothing in this file calls
 * fetch, opens a socket, reads a real clock, or generates a random id.
 */

export type DurableCommandStatus =
  | "draft"
  | "validated"
  | "approval_required"
  | "approved"
  | "rejected"
  | "dry_run_enqueued"
  | "completed"
  | "failed"
  | "blocked";

export type DurableSessionStatus =
  | "planned"
  | "queued"
  | "working"
  | "waiting_for_operator"
  | "result_ready"
  | "reviewing"
  | "completed"
  | "blocked"
  | "failed";

export type DurableApprovalDecision =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_review"
  | "blocked";

export type DurableResultVerdict =
  | "pass"
  | "fail"
  | "blocked"
  | "needs_fix"
  | "warning"
  | "info";

export interface DurableCommandRecordView {
  commandId: string;
  commandType: string;
  status: DurableCommandStatus;
  requestId: string | null;
  sessionId: string | null;
  createdAt: string;
  updatedAt: string | null;
}

export interface DurableSessionRecordView {
  sessionId: string;
  taskId: string | null;
  agentId: string | null;
  runtimeId: string | null;
  status: DurableSessionStatus;
  createdAt: string;
  updatedAt: string | null;
}

export interface DurableEventRecordView {
  eventId: string;
  eventType: string;
  source: string;
  subjectType: string;
  subjectId: string;
  createdAt: string;
  sequence: number;
}

export interface DurableApprovalRecordView {
  approvalId: string;
  approvalType: string;
  subjectType: string;
  subjectId: string;
  decision: DurableApprovalDecision;
  decidedBy: string;
  decidedAt: string;
  reason: string | null;
}

export interface DurableResultRecordView {
  resultId: string;
  resultType: string;
  subjectType: string;
  subjectId: string;
  verdict: DurableResultVerdict;
  createdAt: string;
}

export interface DurableStateCountsView {
  commands: number;
  sessions: number;
  events: number;
  approvals: number;
  results: number;
}

export interface DurableStateSnapshotView {
  schemaVersion: number;
  checkedAt: string;
  dbMode: string;
  walEnabled: boolean;
  dbPath: string;
  counts: DurableStateCountsView;
  disabledCapabilities: Record<string, string>;
  nextStage: string;
}

export interface DurableStateStatusView {
  storeStatus: string;
  stage: string;
  dbPath: string;
  walMode: string;
  eventStreamStatus: string;
  adapterDispatchStatus: string;
  backendSocketServerStatus: string;
}
