export type RenderStatus =
  | "QUEUED"
  | "ANALYZING"
  | "PREPARING"
  | "RENDERING"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface RenderProgressEvent {
  jobId: string;
  status: string;
  progress: number;
  outputPath: string | null;
  error: string | null;
}

export interface RenderSession {
  jobId: string;
  requestedOutputPath: string;
  status: RenderStatus;
  progress: number;
  outputPath: string | null;
  error: string | null;
  busy: boolean;
}

const STATUSES = new Set<RenderStatus>([
  "QUEUED", "ANALYZING", "PREPARING", "RENDERING",
  "VERIFYING", "COMPLETED", "FAILED", "CANCELLED",
]);

function normalizeStatus(status: string): RenderStatus | null {
  return STATUSES.has(status as RenderStatus) ? status as RenderStatus : null;
}

export function isRenderTerminal(status: string): boolean {
  return status === "COMPLETED" || status === "FAILED" || status === "CANCELLED";
}

export function createRenderSession(jobId: string, requestedOutputPath: string): RenderSession {
  return {
    jobId,
    requestedOutputPath,
    status: "QUEUED",
    progress: 0,
    outputPath: null,
    error: null,
    busy: true,
  };
}

export function applyRenderProgress(state: RenderSession, event: RenderProgressEvent): RenderSession {
  if (event.jobId !== state.jobId) return state;
  const status = normalizeStatus(event.status);
  if (!status) {
    return { ...state, status: "FAILED", error: `Unknown render status: ${event.status}`, busy: false };
  }
  const progress = Math.max(state.progress, Math.min(1, Math.max(0, event.progress)));
  return {
    ...state,
    status,
    progress,
    outputPath: event.outputPath ?? state.outputPath,
    error: event.error,
    busy: !isRenderTerminal(status),
  };
}

export function renderStatusText(event: RenderProgressEvent): string {
  const pct = `${Math.round(Math.min(1, Math.max(0, event.progress)) * 100)}%`;
  switch (event.status) {
    case "QUEUED": return "Export queued...";
    case "ANALYZING": return `Analyzing project... ${pct}`;
    case "PREPARING": return `Preparing render... ${pct}`;
    case "RENDERING": return `Rendering... ${pct}`;
    case "VERIFYING": return `Verifying export... ${pct}`;
    case "COMPLETED": return `Exported & verified: ${event.outputPath ?? "output"}`;
    case "FAILED": return `Export failed: ${event.error ?? "unknown render failure"}`;
    case "CANCELLED": return "Export cancelled.";
    default: return `Export failed: unknown render status ${event.status}`;
  }
}
