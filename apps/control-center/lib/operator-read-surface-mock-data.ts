import { buildOperatorReadSurfaceProjection } from "./operator-read-surface-projection";
import type {
  OperatorActivityRecord,
  OperatorHealthSignal,
  OperatorReadSurfaceProjectionState,
} from "./operator-read-surface-types";

const CHECKED_AT = "2026-07-09T18:30:00Z";
const FALLBACK_NOTICE =
  "Stage 7.4 uses deterministic local projection data. Live transport is deferred to Stage 7.5 decision.";

const POPULATED_SIGNALS: OperatorHealthSignal[] = [
  {
    signalId: "ohs-backend",
    signalType: "BACKEND",
    status: "healthy",
    severity: "info",
    summary: "Stage 7.3 operator snapshot builder is projected for review.",
    sourceStage: "Stage 7.3",
    checkedAt: CHECKED_AT,
    references: ["scos/control_center/operator_health_activity.py"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-state",
    signalType: "STATE_STORE",
    status: "healthy",
    severity: "info",
    summary: "Durable state evidence is represented through approved read models.",
    sourceStage: "Stage 7.1",
    checkedAt: CHECKED_AT,
    references: ["ReadSurfaceSnapshot.records"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-event",
    signalType: "EVENT_STREAM",
    status: "healthy",
    severity: "info",
    summary: "Event stream evidence is read-only and projection-safe.",
    sourceStage: "Stage 7.1",
    checkedAt: CHECKED_AT,
    references: ["ReadSurfaceRecord:event_summary"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-approval",
    signalType: "APPROVAL",
    status: "healthy",
    severity: "info",
    summary: "Approval health is visible without mutating approval state.",
    sourceStage: "Stage 7.3",
    checkedAt: CHECKED_AT,
    references: ["OperatorHealthSignal:APPROVAL_HEALTH"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-audit",
    signalType: "AUDIT",
    status: "healthy",
    severity: "info",
    summary: "Audit health is visible through Stage 7.3 metadata.",
    sourceStage: "Stage 7.3",
    checkedAt: CHECKED_AT,
    references: ["OperatorHealthSignal:AUDIT_HEALTH"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-security",
    signalType: "SECURITY_BASELINE",
    status: "healthy",
    severity: "info",
    summary: "Stage 7.2 coherence and non-mutation checks are represented.",
    sourceStage: "Stage 7.2",
    checkedAt: CHECKED_AT,
    references: ["ReadSurfaceCoherenceReport"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-drift",
    signalType: "DRIFT",
    status: "healthy",
    severity: "info",
    summary: "Drift status is visible and not hidden by the projection layer.",
    sourceStage: "Stage 7.3",
    checkedAt: CHECKED_AT,
    references: ["OperatorHealthSignal:DRIFT_STATUS"],
    warnings: [],
    blockers: [],
  },
  {
    signalId: "ohs-host",
    signalType: "HOST_METRICS",
    status: "degraded",
    severity: "warning",
    summary: "Host metrics are projected from static local fixture evidence only.",
    sourceStage: "Stage 7.4",
    checkedAt: CHECKED_AT,
    references: ["apps/control-center/lib/operator-read-surface-mock-data.ts"],
    warnings: ["Live host telemetry is deferred to Stage 7.5 decision."],
    blockers: [],
  },
];

const POPULATED_ACTIVITY: OperatorActivityRecord[] = [
  {
    activityId: "act-stage74",
    activityType: "STATE_ACTIVITY",
    status: "degraded",
    summary: "Stage 7.4 UI projection in progress with local deterministic fixture data.",
    sourceStage: "Stage 7.4",
    occurredAt: "2026-07-09T18:30:00Z",
    referenceLabel: "UI projection fixture",
  },
  {
    activityId: "act-stage73",
    activityType: "EVENT_ACTIVITY",
    status: "healthy",
    summary: "Stage 7.3 operator health and activity read models completed.",
    sourceStage: "Stage 7.3",
    occurredAt: "2026-07-09T18:20:00Z",
    referenceLabel: "a690534",
  },
  {
    activityId: "act-stage72",
    activityType: "SECURITY_ACTIVITY",
    status: "healthy",
    summary: "Stage 7.2 read surface coherence gate complete.",
    sourceStage: "Stage 7.2",
    occurredAt: "2026-07-09T18:10:00Z",
    referenceLabel: "ReadSurfaceCoherenceReport",
  },
  {
    activityId: "act-stage71",
    activityType: "COMMAND_ACTIVITY",
    status: "healthy",
    summary: "Stage 7.1 local read query surface complete.",
    sourceStage: "Stage 7.1",
    occurredAt: "2026-07-09T18:00:00Z",
    referenceLabel: "ReadSurfaceResult",
  },
];

export const populatedOperatorReadSurfaceProjection: OperatorReadSurfaceProjectionState =
  buildOperatorReadSurfaceProjection({
    projectionId: "operator-read-surface-populated",
    state: "populated",
    readiness: {
      goNoGo: "GO",
      readinessScore: 94,
      checkedAt: CHECKED_AT,
      totalHealthSignals: 8,
      blockersCount: 0,
      warningsCount: 1,
      degradedOrStaleCount: 1,
    },
    healthSignals: POPULATED_SIGNALS,
    recentActivity: POPULATED_ACTIVITY,
    coherence: {
      status: "healthy",
      checkedAt: CHECKED_AT,
      inspectedSources: [
        "Stage 7.1 Read Surface Result",
        "Stage 7.2 Coherence Gate",
        "Stage 7.3 Operator Snapshot",
      ],
      blockers: [],
      warnings: ["Stage 7.5 live sync transport is pending approval."],
      fallbackModeNote: FALLBACK_NOTICE,
    },
    fallbackNotice: FALLBACK_NOTICE,
  });

export const loadingOperatorReadSurfaceProjection: OperatorReadSurfaceProjectionState =
  buildOperatorReadSurfaceProjection({
    projectionId: "operator-read-surface-loading",
    state: "loading",
    readiness: { checkedAt: CHECKED_AT, goNoGo: "GO", readinessScore: 0 },
    coherence: {
      status: "unknown",
      checkedAt: CHECKED_AT,
      fallbackModeNote: FALLBACK_NOTICE,
    },
    fallbackNotice: FALLBACK_NOTICE,
  });

export const emptyOperatorReadSurfaceProjection: OperatorReadSurfaceProjectionState =
  buildOperatorReadSurfaceProjection({
    projectionId: "operator-read-surface-empty",
    state: "empty",
    readiness: { checkedAt: CHECKED_AT, goNoGo: "GO", readinessScore: 0 },
    coherence: {
      status: "missing",
      checkedAt: CHECKED_AT,
      warnings: ["No operator projection records are available in the local fixture."],
      fallbackModeNote: FALLBACK_NOTICE,
    },
    fallbackNotice: FALLBACK_NOTICE,
  });

export const degradedOperatorReadSurfaceProjection: OperatorReadSurfaceProjectionState =
  buildOperatorReadSurfaceProjection({
    ...populatedOperatorReadSurfaceProjection,
    projectionId: "operator-read-surface-degraded",
    state: "degraded",
    readiness: {
      ...populatedOperatorReadSurfaceProjection.readiness,
      readinessScore: 82,
      warningsCount: 3,
      degradedOrStaleCount: 2,
    },
    healthSignals: POPULATED_SIGNALS.map((signal) =>
      signal.signalType === "DRIFT"
        ? {
            ...signal,
            status: "stale",
            severity: "warning",
            warnings: ["Drift evidence is stale in this deterministic fixture."],
          }
        : signal,
    ),
    coherence: {
      ...populatedOperatorReadSurfaceProjection.coherence,
      status: "degraded",
      warnings: [
        "Stage 7.5 live sync transport is pending approval.",
        "Drift evidence is stale in this deterministic fixture.",
      ],
    },
  });

export const errorOperatorReadSurfaceProjection: OperatorReadSurfaceProjectionState =
  buildOperatorReadSurfaceProjection({
    ...populatedOperatorReadSurfaceProjection,
    projectionId: "operator-read-surface-error",
    state: "error",
    readiness: {
      ...populatedOperatorReadSurfaceProjection.readiness,
      goNoGo: "NO_GO",
      readinessScore: 62,
      blockersCount: 1,
      warningsCount: 1,
    },
    healthSignals: POPULATED_SIGNALS.map((signal) =>
      signal.signalType === "SECURITY_BASELINE"
        ? {
            ...signal,
            status: "error",
            severity: "error",
            blockers: ["Coherence blocker visible in error fixture."],
          }
        : {
            ...signal,
            status: "unknown",
            severity: "warning",
            warnings: ["Health evidence is withheld while coherence is blocked."],
          },
    ),
    recentActivity: POPULATED_ACTIVITY.map((record) => ({
      ...record,
      status: record.activityId === "act-stage74" ? "error" : "unknown",
    })),
    coherence: {
      ...populatedOperatorReadSurfaceProjection.coherence,
      status: "error",
      blockers: ["Coherence blocker visible in error fixture."],
    },
  });
