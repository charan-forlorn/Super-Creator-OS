// SCOS Control Center - Stage 5.10 Stage 5 Final AI Command Center
// Certification types. Static frontend mirror only. SCOS does not execute
// anything here: no backend calls, no persistence, no network behavior.
// Real contracts live in scos/control_center/stage5_certification_models.py
// and scos/control_center/stage5_final_certification.py.

export type CertificationCheckStatus = "success" | "failure" | "skipped";

export type CertificationSeverity = "info" | "warning" | "error" | "critical";

export type CertificationCategory =
  | "preflight"
  | "source_contract"
  | "workflow_continuity"
  | "safety_boundary"
  | "frontend_static_scope"
  | "testing"
  | "security"
  | "stage5_readiness"
  | "stage6_handoff";

export type BlockerSeverity = "warning" | "error" | "critical";

export type HandoffPriority = "low" | "normal" | "high" | "urgent";

export type GoNoGo = "GO" | "NO_GO";

export type ReadinessLevel = "certified" | "conditionally_ready" | "blocked";

export interface Stage5CertificationCheckView {
  checkName: string;
  status: CertificationCheckStatus;
  severity: CertificationSeverity;
  category: CertificationCategory;
  artifactPath: string | null;
  errorKind: string | null;
  errorDetail: string | null;
}

export interface Stage5CertificationBlockerView {
  blockerId: string;
  category: CertificationCategory;
  severity: BlockerSeverity;
  title: string;
  detail: string;
  recommendedAction: string;
  sourceCheck: string;
}

export interface Stage6HandoffItemView {
  itemId: string;
  title: string;
  category: string;
  priority: HandoffPriority;
  description: string;
  stage6Owner: string;
  sourceStage5Evidence: string | null;
}

export interface Stage5FinalCertificationResultView {
  certificationId: string;
  checkedAt: string;
  stage: string;
  stageClosed: boolean;
  goNoGo: GoNoGo;
  readinessLevel: ReadinessLevel;
  readinessScore: number;
  readinessMaxScore: number;
  checks: readonly Stage5CertificationCheckView[];
  blockers: readonly Stage5CertificationBlockerView[];
  stage6HandoffItems: readonly Stage6HandoffItemView[];
}
