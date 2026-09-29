export type OperatorReadSurfaceStatus =
  | "healthy"
  | "degraded"
  | "stale"
  | "missing"
  | "error"
  | "blocked"
  | "unknown";

export type OperatorHealthSignalType =
  | "BACKEND"
  | "STATE_STORE"
  | "EVENT_STREAM"
  | "APPROVAL"
  | "AUDIT"
  | "SECURITY_BASELINE"
  | "DRIFT"
  | "HOST_METRICS";

export type OperatorReadSurfaceProjectionKind =
  | "loading"
  | "empty"
  | "populated"
  | "degraded"
  | "error";

export interface OperatorHealthSignal {
  signalId: string;
  signalType: OperatorHealthSignalType;
  status: OperatorReadSurfaceStatus;
  severity: "info" | "warning" | "error" | "critical";
  summary: string;
  sourceStage: string;
  checkedAt: string;
  references: string[];
  warnings: string[];
  blockers: string[];
}

export interface OperatorActivityRecord {
  activityId: string;
  activityType:
    | "COMMAND_ACTIVITY"
    | "APPROVAL_ACTIVITY"
    | "AUDIT_ACTIVITY"
    | "EVENT_ACTIVITY"
    | "STATE_ACTIVITY"
    | "SECURITY_ACTIVITY"
    | "DRIFT_ACTIVITY";
  status: OperatorReadSurfaceStatus;
  summary: string;
  sourceStage: string;
  occurredAt: string;
  referenceLabel: string;
}

export interface OperatorReadinessSummary {
  goNoGo: "GO" | "NO_GO";
  readinessScore: number;
  checkedAt: string;
  totalHealthSignals: number;
  blockersCount: number;
  warningsCount: number;
  degradedOrStaleCount: number;
}

export interface ReadSurfaceCoherenceSummary {
  status: OperatorReadSurfaceStatus;
  checkedAt: string;
  inspectedSources: string[];
  blockers: string[];
  warnings: string[];
  fallbackModeNote: string;
}

export interface OperatorReadSurfaceProjection {
  projectionId: string;
  state: OperatorReadSurfaceProjectionKind;
  readiness: OperatorReadinessSummary;
  healthSignals: OperatorHealthSignal[];
  recentActivity: OperatorActivityRecord[];
  coherence: ReadSurfaceCoherenceSummary;
  fallbackNotice: string;
}

export interface OperatorReadSurfaceProjectionInput {
  projectionId?: string;
  state?: OperatorReadSurfaceProjectionKind;
  readiness?: Partial<OperatorReadinessSummary>;
  healthSignals?: OperatorHealthSignal[];
  recentActivity?: OperatorActivityRecord[];
  coherence?: Partial<ReadSurfaceCoherenceSummary>;
  fallbackNotice?: string;
}

export type OperatorReadSurfaceProjectionState = OperatorReadSurfaceProjection;
