export const OPERATOR_DRY_RUN_SCHEMA_VERSION = "scos.operator-dry-run.v1/1.0.0";

export type OperatorDryRunOperation = "inspect-project" | "initialize-project" | "prepare-render";
export type OperatorDryRunStatus = "READY" | "BLOCKED" | "INVALID" | "UNAVAILABLE";
export type OperatorDryRunAuthorizationStatus =
  | "AUTHORIZED_FOR_PREVIEW"
  | "NOT_AUTHORIZED"
  | "AUTHORIZATION_UNAVAILABLE"
  | "AUTHORIZATION_MALFORMED"
  | "AUTHORIZATION_STALE"
  | "NOT_APPLICABLE";

export interface OperatorDryRunRequest {
  request_id: string;
  operation: OperatorDryRunOperation;
  dry_run: true;
  parameters: Record<string, string>;
  requested_at: string;
  schema_version: typeof OPERATOR_DRY_RUN_SCHEMA_VERSION;
}

export interface OperatorDryRunResponse {
  request_id: string;
  operation: string;
  mode: "DRY_RUN";
  status: OperatorDryRunStatus;
  authorization: { status: OperatorDryRunAuthorizationStatus; reason_codes: string[] };
  prerequisites: { id: string; status: "READY" | "BLOCKED" | "UNAVAILABLE"; reason_code: string }[];
  normalized_parameters: Record<string, string>;
  proposed_actions: { order: number; action: string; target: string }[];
  prohibited_actions: { order: number; action: string; operation: string }[];
  warnings: string[];
  reason_codes: string[];
  side_effects_performed: false;
  generated_at: string;
  schema_version: typeof OPERATOR_DRY_RUN_SCHEMA_VERSION;
  preview_id: string;
}

const operations: OperatorDryRunOperation[] = ["inspect-project", "initialize-project", "prepare-render"];
const forbiddenFields = new Set([
  "command",
  "shell",
  "argv",
  "executable",
  "script",
  "code",
  "eval",
  "url",
  "callback",
  "webhook",
  "environment",
  "env",
  "working_directory",
]);
const allowedParams: Record<OperatorDryRunOperation, Set<string>> = {
  "inspect-project": new Set(["project_id"]),
  "initialize-project": new Set(["project_id", "title", "language"]),
  "prepare-render": new Set(["project_id", "render_profile"]),
};

function stablePreviewId(requestId: string, operation: string, reasons: string[]): string {
  const text = `${requestId}|${operation}|${[...reasons].sort().join(",")}`;
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  return `odr-${hash.toString(16).padStart(8, "0")}`;
}

function validText(value: unknown, field: string, maxLen = 120): [string | null, string[]] {
  if (typeof value !== "string") return [null, [`${field.toUpperCase()}_MUST_BE_STRING`]];
  const text = value.trim();
  if (!text) return [null, [`${field.toUpperCase()}_REQUIRED`]];
  if (text.length > maxLen) return [null, [`${field.toUpperCase()}_TOO_LONG`]];
  if (/[\r\n\t]/.test(text)) return [null, [`${field.toUpperCase()}_CONTROL_CHAR_REJECTED`]];
  return [text, []];
}

function safeProjectId(value: string): boolean {
  return /^[A-Za-z0-9_.-]+$/.test(value);
}

function prohibitedActions(operation: string) {
  return [
    "invoke_hvs",
    "start_subprocess",
    "start_ffmpeg_or_ffprobe",
    "write_project_or_contract",
    "write_approval_or_authorization",
    "write_runtime_journal",
    "enqueue_or_dispatch_work",
    "claim_worker_lease",
    "perform_network_call",
    "write_browser_storage",
  ].map((action, index) => ({ order: index + 1, action, operation }));
}

function invalidResponse(requestId: string, operation: string, reasonCodes: string[]): OperatorDryRunResponse {
  const sorted = [...new Set(reasonCodes)].sort();
  return {
    request_id: requestId || "INVALID_REQUEST",
    operation: operation || "unknown",
    mode: "DRY_RUN",
    status: "INVALID",
    authorization: { status: "NOT_APPLICABLE", reason_codes: [] },
    prerequisites: [],
    normalized_parameters: {},
    proposed_actions: [],
    prohibited_actions: prohibitedActions(operation || "unknown"),
    warnings: [],
    reason_codes: sorted,
    side_effects_performed: false,
    generated_at: "DRY_RUN_TIME_SUPPLIED_BY_ROUTE",
    schema_version: OPERATOR_DRY_RUN_SCHEMA_VERSION,
    preview_id: stablePreviewId(requestId, operation, sorted),
  };
}

export function planOperatorDryRun(raw: unknown): OperatorDryRunResponse {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return invalidResponse("INVALID_REQUEST", "unknown", ["REQUEST_MUST_BE_OBJECT"]);
  }
  const payload = raw as Record<string, unknown>;
  const allowedTop = new Set(["request_id", "operation", "dry_run", "parameters", "requested_at", "schema_version"]);
  const errors: string[] = [];
  for (const key of Object.keys(payload)) {
    if (!allowedTop.has(key)) errors.push("UNKNOWN_TOP_LEVEL_FIELD");
    if (forbiddenFields.has(key)) errors.push("FORBIDDEN_TOP_LEVEL_FIELD");
  }
  const [requestId, requestIdErrors] = validText(payload.request_id, "request_id", 80);
  const [operationRaw, operationErrors] = validText(payload.operation, "operation", 40);
  const [requestedAt, requestedAtErrors] = validText(payload.requested_at, "requested_at", 80);
  errors.push(...requestIdErrors, ...operationErrors, ...requestedAtErrors);
  if (payload.schema_version !== OPERATOR_DRY_RUN_SCHEMA_VERSION) errors.push("SCHEMA_VERSION_UNSUPPORTED");
  if (payload.dry_run !== true) errors.push("DRY_RUN_MUST_BE_TRUE");
  const operation = operationRaw as OperatorDryRunOperation | null;
  if (!operation || !operations.includes(operation)) errors.push("UNKNOWN_OPERATION");
  const paramsRaw = payload.parameters;
  const params = paramsRaw && typeof paramsRaw === "object" && !Array.isArray(paramsRaw) ? (paramsRaw as Record<string, unknown>) : null;
  if (!params) errors.push("PARAMETERS_MUST_BE_OBJECT");
  const normalized: Record<string, string> = {};
  const allowed = operation && operations.includes(operation) ? allowedParams[operation] : new Set<string>();
  if (params) {
    for (const key of Object.keys(params)) {
      if (!allowed.has(key)) errors.push("UNKNOWN_PARAMETER_FIELD");
      if (forbiddenFields.has(key)) errors.push("FORBIDDEN_PARAMETER_FIELD");
      if (allowed.has(key)) {
        const [value, valueErrors] = validText(params[key], key);
        errors.push(...valueErrors);
        if (value) normalized[key] = value;
      }
    }
  }
  if (!normalized.project_id) errors.push("PROJECT_ID_REQUIRED");
  if (normalized.project_id && !safeProjectId(normalized.project_id)) errors.push("PROJECT_ID_UNSAFE");
  if (operation === "initialize-project") {
    if (!normalized.title) errors.push("TITLE_REQUIRED");
    if (!new Set(["en", "th"]).has(normalized.language)) errors.push("LANGUAGE_UNSUPPORTED");
  }
  if (operation === "prepare-render" && normalized.render_profile && !new Set(["vertical", "standard"]).has(normalized.render_profile)) {
    errors.push("RENDER_PROFILE_UNSUPPORTED");
  }
  if (errors.length || !requestId || !operation || !requestedAt) return invalidResponse(requestId ?? "INVALID_REQUEST", operationRaw ?? "unknown", errors);

  const authStatus: OperatorDryRunAuthorizationStatus = operation === "inspect-project" ? "NOT_APPLICABLE" : "AUTHORIZATION_UNAVAILABLE";
  const authCodes = operation === "inspect-project" ? ["AUTH_NOT_REQUIRED_FOR_READ_ONLY_PREVIEW"] : ["AUTHORIZATION_EVALUATOR_INPUT_MISSING"];
  const prerequisites = operation === "prepare-render"
    ? [
        { id: "render_inputs", status: "BLOCKED" as const, reason_code: "RENDER_INPUTS_NOT_VERIFIED_IN_DRY_RUN" },
        { id: "request_validation", status: "READY" as const, reason_code: "REQUEST_VALIDATED" },
      ]
    : [
        { id: "request_validation", status: "READY" as const, reason_code: "REQUEST_VALIDATED" },
        { id: operation === "initialize-project" ? "project_creation" : "project_lookup", status: "READY" as const, reason_code: operation === "initialize-project" ? "PROJECT_CREATION_CAN_BE_PREVIEWED_ONLY" : "READ_ONLY_LOOKUP_CAN_BE_PREVIEWED" },
      ];
  const status: OperatorDryRunStatus = operation === "inspect-project" ? "READY" : "UNAVAILABLE";
  const proposed = operation === "inspect-project"
    ? ["VALIDATE_PROJECT_REFERENCE", "READ_ONLY_PROJECT_LOOKUP_PREVIEW"]
    : operation === "initialize-project"
      ? ["VALIDATE_INITIALIZATION_PARAMETERS", "EVALUATE_AUTHORIZATION_FOR_PREVIEW_ONLY", "DESCRIBE_PROJECT_CREATION_PLAN"]
      : ["VALIDATE_RENDER_REFERENCE", "EVALUATE_RENDER_PREREQUISITES_FOR_PREVIEW_ONLY", "DESCRIBE_RENDER_PLAN_WITHOUT_RENDERING"];
  const reasonCodes = [...authCodes, ...prerequisites.map((item) => item.reason_code), "SIDE_EFFECTS_ZERO"].sort();
  return {
    request_id: requestId,
    operation,
    mode: "DRY_RUN",
    status,
    authorization: { status: authStatus, reason_codes: authCodes },
    prerequisites,
    normalized_parameters: Object.fromEntries(Object.entries(normalized).sort()),
    proposed_actions: proposed.map((action, index) => ({ order: index + 1, action, target: normalized.project_id })),
    prohibited_actions: prohibitedActions(operation),
    warnings: ["DRY_RUN_PREVIEW_ONLY", "LIVE_EXECUTION_NOT_ENABLED"],
    reason_codes: reasonCodes,
    side_effects_performed: false,
    generated_at: "DRY_RUN_TIME_SUPPLIED_BY_ROUTE",
    schema_version: OPERATOR_DRY_RUN_SCHEMA_VERSION,
    preview_id: stablePreviewId(requestId, operation, reasonCodes),
  };
}

export function buildDryRunRequest(operation: OperatorDryRunOperation, parameters: Record<string, string>): OperatorDryRunRequest {
  return {
    request_id: `odr-${operation}`,
    operation,
    dry_run: true,
    parameters,
    requested_at: "DRY_RUN_TIME_SUPPLIED_BY_CLIENT",
    schema_version: OPERATOR_DRY_RUN_SCHEMA_VERSION,
  };
}
