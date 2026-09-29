import type {
  OperatorActivityRecord,
  OperatorHealthSignal,
  OperatorHealthSignalType,
  OperatorReadSurfaceProjection,
  OperatorReadSurfaceProjectionInput,
  OperatorReadSurfaceProjectionKind,
  OperatorReadSurfaceProjectionState,
  OperatorReadSurfaceStatus,
} from "./operator-read-surface-types";

const SIGNAL_ORDER: OperatorHealthSignalType[] = [
  "BACKEND",
  "STATE_STORE",
  "EVENT_STREAM",
  "APPROVAL",
  "AUDIT",
  "SECURITY_BASELINE",
  "DRIFT",
  "HOST_METRICS",
];

const DEFAULT_CHECKED_AT = "2026-07-09T00:00:00Z";
const FALLBACK_NOTICE =
  "Stage 7.4 uses deterministic local projection data. Live transport is deferred to Stage 7.5 decision.";

function signalOrder(signal: OperatorHealthSignal): number {
  const index = SIGNAL_ORDER.indexOf(signal.signalType);
  return index === -1 ? SIGNAL_ORDER.length : index;
}

function hasRequiredProjectionData(input: OperatorReadSurfaceProjectionInput): boolean {
  return Boolean(
    input.readiness &&
      input.coherence &&
      Array.isArray(input.healthSignals) &&
      Array.isArray(input.recentActivity),
  );
}

function deriveProjectionState(
  input: OperatorReadSurfaceProjectionInput,
): OperatorReadSurfaceProjectionKind {
  if (input.state) return input.state;
  if (!hasRequiredProjectionData(input)) return "empty";
  if ((input.coherence?.blockers?.length ?? 0) > 0) return "error";
  if (
    (input.coherence?.warnings?.length ?? 0) > 0 ||
    input.healthSignals?.some((signal) =>
      ["degraded", "stale", "missing", "unknown"].includes(signal.status),
    )
  ) {
    return "degraded";
  }
  return "populated";
}

function normalizeHealthSignals(
  signals: OperatorHealthSignal[] | undefined,
): OperatorHealthSignal[] {
  return [...(signals ?? [])].sort(
    (left, right) =>
      signalOrder(left) - signalOrder(right) ||
      left.signalId.localeCompare(right.signalId),
  );
}

export function filterActivityByLimit(
  records: OperatorActivityRecord[],
  limit: number,
): OperatorActivityRecord[] {
  const normalizedLimit = Math.max(0, Math.trunc(limit));
  return [...records]
    .sort(
      (left, right) =>
        right.occurredAt.localeCompare(left.occurredAt) ||
        right.activityId.localeCompare(left.activityId),
    )
    .slice(0, normalizedLimit);
}

export function getReadinessTone(summary: { goNoGo: "GO" | "NO_GO"; readinessScore: number }): string {
  if (summary.goNoGo === "NO_GO") return "bg-status-rejected/15 text-status-rejected ring-status-rejected/30";
  if (summary.readinessScore < 90) return "bg-status-review/15 text-status-review ring-status-review/30";
  return "bg-status-approved/15 text-status-approved ring-status-approved/30";
}

export function getSignalTone(status: OperatorReadSurfaceStatus): string {
  switch (status) {
    case "healthy":
      return "bg-status-approved/15 text-status-approved ring-status-approved/30";
    case "degraded":
    case "stale":
    case "missing":
    case "unknown":
      return "bg-status-review/15 text-status-review ring-status-review/30";
    case "blocked":
    case "error":
      return "bg-status-rejected/15 text-status-rejected ring-status-rejected/30";
    default:
      return "bg-surface-2 text-ink-faint ring-border";
  }
}

export function countBlockersAndWarnings(projection: OperatorReadSurfaceProjection): {
  blockers: number;
  warnings: number;
} {
  const signalBlockers = projection.healthSignals.reduce(
    (count, signal) => count + signal.blockers.length,
    0,
  );
  const signalWarnings = projection.healthSignals.reduce(
    (count, signal) => count + signal.warnings.length,
    0,
  );
  return {
    blockers: projection.coherence.blockers.length + signalBlockers,
    warnings: projection.coherence.warnings.length + signalWarnings,
  };
}

export function buildOperatorReadSurfaceProjection(
  input: OperatorReadSurfaceProjectionInput,
): OperatorReadSurfaceProjectionState {
  const state = deriveProjectionState(input);
  const healthSignals = normalizeHealthSignals(input.healthSignals);
  const recentActivity = filterActivityByLimit(input.recentActivity ?? [], 25);
  const checkedAt =
    input.readiness?.checkedAt ?? input.coherence?.checkedAt ?? DEFAULT_CHECKED_AT;
  const fallbackNotice = input.fallbackNotice ?? FALLBACK_NOTICE;
  const coherence = {
    status: input.coherence?.status ?? (state === "error" ? "error" : "unknown"),
    checkedAt,
    inspectedSources: [...(input.coherence?.inspectedSources ?? [])].sort(),
    blockers: [...(input.coherence?.blockers ?? [])].sort(),
    warnings: [...(input.coherence?.warnings ?? [])].sort(),
    fallbackModeNote: input.coherence?.fallbackModeNote ?? fallbackNotice,
  };
  const blockersCount =
    input.readiness?.blockersCount ??
    coherence.blockers.length +
      healthSignals.reduce((count, signal) => count + signal.blockers.length, 0);
  const warningsCount =
    input.readiness?.warningsCount ??
    coherence.warnings.length +
      healthSignals.reduce((count, signal) => count + signal.warnings.length, 0);
  const degradedOrStaleCount =
    input.readiness?.degradedOrStaleCount ??
    healthSignals.filter((signal) =>
      ["degraded", "stale", "missing", "unknown"].includes(signal.status),
    ).length;

  return {
    projectionId: input.projectionId ?? `operator-read-surface-${state}`,
    state,
    readiness: {
      goNoGo: input.readiness?.goNoGo ?? (blockersCount > 0 ? "NO_GO" : "GO"),
      readinessScore: input.readiness?.readinessScore ?? (blockersCount > 0 ? 70 : 100),
      checkedAt,
      totalHealthSignals: input.readiness?.totalHealthSignals ?? healthSignals.length,
      blockersCount,
      warningsCount,
      degradedOrStaleCount,
    },
    healthSignals,
    recentActivity,
    coherence,
    fallbackNotice,
  };
}
