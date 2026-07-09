export type ApprovalState =
  | "pending"
  | "approved"
  | "denied"
  | "missing_approval"
  | "tampered"
  | "executed"
  | "blocked"
  | "unknown";

export type ExecutionState =
  | "not_executed"
  | "executed"
  | "blocked_missing_approval"
  | "blocked_denied"
  | "blocked_tampered_approval"
  | "blocked_not_allowlisted"
  | "blocked_validation_failed"
  | "unknown";

export type AuditState = "audited" | "missing" | "tampered" | "unknown";
export type EventState = "present" | "missing" | "unknown";

export interface OperatorCommandEvidenceReference {
  referenceId: string;
  referenceType: "approval" | "audit" | "event" | "queue" | "result" | "state";
  sourceStage: string;
  path: string;
  exists: boolean;
  readable: boolean;
  digest: string | null;
}

export interface OperatorCommandApprovalState {
  commandId: string;
  approvalState: ApprovalState;
  terminal: boolean;
  humanReadableStatus: string;
  requiredOperatorAction: string;
  evidenceReferences: OperatorCommandEvidenceReference[];
}

export interface ExecutionEvidenceRecord {
  evidenceId: string;
  commandId: string;
  executionState: ExecutionState;
  approvalState: ApprovalState;
  auditState: AuditState;
  eventState: EventState;
  summary: string;
  references: OperatorCommandEvidenceReference[];
  metadata: Array<[string, string]>;
}

export interface OperatorCommandView {
  viewId: string;
  checkedAt: string;
  commandId: string;
  commandType: string;
  approval: OperatorCommandApprovalState;
  execution: ExecutionEvidenceRecord;
  warnings: string[];
  blockers: string[];
  nextManualAction: string;
}

export interface OperatorCommandViewTotals {
  pending: number;
  approved: number;
  denied: number;
  missingApproval: number;
  executed: number;
  blocked: number;
  audited: number;
}

export interface OperatorCommandViewSnapshot {
  snapshotId: string;
  checkedAt: string;
  views: OperatorCommandView[];
  totals: OperatorCommandViewTotals;
  warnings: string[];
  blockers: string[];
  readinessScore: number;
  goNoGo: "GO" | "NO_GO";
  accepted: boolean;
}
