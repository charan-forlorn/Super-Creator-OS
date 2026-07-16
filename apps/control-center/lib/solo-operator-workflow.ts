export const SOLO_OPERATOR_SCHEMA_VERSION = "scos.solo-operator-control-loop.v1";

export type SoloWorkflowStatus =
  | "approval_required"
  | "approved"
  | "rejected"
  | "dry_run_succeeded"
  | "blocked";

export interface SoloWorkflowRequest {
  workflow: "video-production";
  project_id: string;
  title: string;
  language: "en" | "th";
  render_profile: "vertical" | "standard";
  idempotency_key: string;
}

export interface SoloWorkflowProjection {
  ok: boolean;
  schema_version: typeof SOLO_OPERATOR_SCHEMA_VERSION;
  command_id: string;
  status: SoloWorkflowStatus;
  workflow: "video-production";
  checked_at: string;
  approval_required: boolean;
  dry_run_only: true;
  side_effects_performed: false;
  approval_count: number;
  result_count: number;
  safe_result_summary: string | null;
  next_operator_action: string;
  errors: string[];
}

function stableId(prefix: string, text: string): string {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${prefix}${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function validateSoloWorkflowRequest(request: SoloWorkflowRequest): string[] {
  const errors: string[] = [];
  if (request.workflow !== "video-production") errors.push("WORKFLOW_UNSUPPORTED");
  if (!/^[A-Za-z0-9_.-]+$/.test(request.project_id.trim())) errors.push("PROJECT_ID_UNSAFE");
  if (!request.title.trim()) errors.push("TITLE_REQUIRED");
  if (!["en", "th"].includes(request.language)) errors.push("LANGUAGE_UNSUPPORTED");
  if (!["vertical", "standard"].includes(request.render_profile)) errors.push("RENDER_PROFILE_UNSUPPORTED");
  if (!request.idempotency_key.trim()) errors.push("IDEMPOTENCY_KEY_REQUIRED");
  return [...new Set(errors)].sort();
}

export function initialSoloProjection(request: SoloWorkflowRequest, checkedAt = "UI_TIME_SUPPLIED_BY_CLIENT"): SoloWorkflowProjection {
  const errors = validateSoloWorkflowRequest(request);
  return {
    ok: errors.length === 0,
    schema_version: SOLO_OPERATOR_SCHEMA_VERSION,
    command_id: stableId("soc-", `${request.idempotency_key}|${request.project_id}|${request.title}|${request.language}|${request.render_profile}`),
    status: errors.length ? "blocked" : "approval_required",
    workflow: "video-production",
    checked_at: checkedAt,
    approval_required: errors.length === 0,
    dry_run_only: true,
    side_effects_performed: false,
    approval_count: 0,
    result_count: 0,
    safe_result_summary: null,
    next_operator_action: errors.length ? "Fix validation errors before approval." : "Approve or reject the request.",
    errors,
  };
}

export function approveSoloProjection(projection: SoloWorkflowProjection): SoloWorkflowProjection {
  if (projection.status !== "approval_required") return projection;
  return {
    ...projection,
    status: "approved",
    approval_required: false,
    approval_count: 1,
    next_operator_action: "Dispatch the fake HVS dry-run.",
  };
}

export function rejectSoloProjection(projection: SoloWorkflowProjection): SoloWorkflowProjection {
  if (projection.status !== "approval_required") return projection;
  return {
    ...projection,
    status: "rejected",
    approval_required: false,
    approval_count: 1,
    next_operator_action: "Submit a new request if work is still needed.",
  };
}

export function dispatchSoloProjection(projection: SoloWorkflowProjection): SoloWorkflowProjection {
  if (projection.status === "dry_run_succeeded") return projection;
  if (projection.status !== "approved") {
    return { ...projection, status: "blocked", errors: ["DISPATCH_REQUIRES_APPROVAL"], next_operator_action: "Approve before dispatch." };
  }
  return {
    ...projection,
    status: "dry_run_succeeded",
    result_count: 1,
    safe_result_summary: "Fake HVS dry-run succeeded; no live render executed.",
    next_operator_action: "Inspect the dry-run result summary.",
  };
}
