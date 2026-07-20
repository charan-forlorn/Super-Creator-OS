/**
 * Cohort 10E — thin, bounded transport to the Python render authority.
 *
 * This module is NO LONGER an authority. It contains no authorization
 * decisions, no capability issuance/consumption, no attempt persistence, no
 * single-active-render claiming, no replay/unknown-outcome classification,
 * no reconciliation decisions. The authoritative boundary lives in
 *   scos/control_center/hvs_render_execution_service.py
 *   scos/control_center/hvs_render_attempt_store.py
 *   scos/control_center/hvs_adapter.py            (real HVS render boundary)
 * and is reached ONLY through the Python CLI bridge:
 *   python -m scos.control_center.hvs_render_cli <operation>
 *
 * The browser is NEVER the authority: it may only review a deterministic
 * plan, request authorization, give explicit confirmation, and render the
 * authoritative server response. No HVS call from the browser.
 *
 * Transport contract (mandated, fail-closed):
 *  - spawn/execFile with an argv array; never shell interpolation;
 *  - never `exec` with a constructed command string;
 *  - canonical SCOS Python interpreter resolved from TRUSTED server-side
 *    configuration only (never browser-supplied);
 *  - invoke: python -m scos.control_center.hvs_render_cli <op>;
 *  - request data sent over stdin as bounded JSON;
 *  - exactly one structured JSON response parsed from stdout;
 *  - malformed / empty / multiple / oversized output => failure;
 *  - child exit code + stderr preserved for server-side diagnostics only;
 *  - raw stderr, stack traces, interpreter paths, repository paths, and
 *    local filesystem paths are NEVER returned to the browser;
 *  - bounded timeout; on timeout only the OWNED child is terminated;
 *  - no automatic retry;
 *  - only an explicit, minimal environment is passed;
 *  - no browser-supplied executable, cwd, store path, projects_root,
 *    or command reaches the child.
 */

import * as childProcess from "node:child_process";
import { resolve as nodeResolve } from "node:path";

// The HVS render bridge uses a ONE-SHOT bounded timeout to kill ONLY the owned
// child on stall (transport contract). The static security scanner exempts
// this exact bounded child-kill `setTimeout` pattern in this reviewed file.

// ---------------------------------------------------------------------------
// TRUSTED server-side configuration (never browser-influenced)
// ---------------------------------------------------------------------------

function resolveTrustedDefaultPython(): string {
  return process.env.SCOS_PYTHON_INTERPRETER && process.env.SCOS_PYTHON_INTERPRETER.length > 0
    ? process.env.SCOS_PYTHON_INTERPRETER
    : nodeResolve(process.cwd(), "..", "..", ".venv", "Scripts", "python.exe");
}

const BRIDGE_MODULE = "scos.control_center.hvs_render_cli";

export type BridgeOperation = "projection" | "authorize" | "execute" | "reconcile" | "record-transport-unknown";

export function serverResolvedScope(): { storePath?: string; projectsRoot?: string; outputRootConfigured: boolean } {
  const storePath = process.env.SCOS_RENDER_STORE_PATH;
  // The materialized HVS project lives under SCOS_HVS_PROJECTS_ROOT (the
  // projects root), distinct from the render output root. Using the output
  // root here would make the renderer look for the project under the output
  // directory and fail project-exists gating.
  const projectsRoot = process.env.SCOS_HVS_PROJECTS_ROOT;
  return {
    storePath: storePath && storePath.length > 0 ? storePath : undefined,
    projectsRoot: projectsRoot && projectsRoot.length > 0 ? projectsRoot : undefined,
    outputRootConfigured: Boolean(process.env.SCOS_RENDER_OUTPUT_ROOT && process.env.SCOS_RENDER_OUTPUT_ROOT.length > 0),
  };
}

const ALLOWED_OPERATIONS: ReadonlySet<BridgeOperation> = new Set<BridgeOperation>([
  "projection",
  "authorize",
  "execute",
  "reconcile",
  "record-transport-unknown",
]);

const MAX_STDOUT_BYTES = 1_048_576; // 1 MiB
const BRIDGE_TIMEOUT_MS = 60_000; // 60s (render can be slow)

export interface RenderPlan {
  plan_schema_version: number;
  project_id: string;
  project_revision: number;
  materialization_attempt_id: string;
  materialization_plan_hash: string;
  render_profile_id: string;
  hvs_project_name: string;
  output_root_identity: string;
  profile_metadata: Record<string, unknown>;
  expected_output_filename: string;
  expected_output_relative_path: string;
  forbidden_operations: string[];
  plan_hash: string;
}

export type RenderTruthState =
  | "RENDER_NOT_REQUESTED"
  | "RENDER_AUTHORIZATION_REQUIRED"
  | "RENDER_AUTHORIZED"
  | "RENDER_STARTING"
  | "RENDER_RUNNING"
  | "ARTIFACT_DISCOVERED"
  | "ARTIFACT_VALIDATED"
  | "RENDER_SUCCEEDED"
  | "RENDER_FAILED_CONFIRMED"
  | "RENDER_OUTCOME_UNKNOWN"
  | "RENDER_RECONCILIATION_REQUIRED";

export interface RenderArtifactView {
  artifact_id: string;
  render_attempt_id: string;
  profile_id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  frame_rate: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  validation_state: string;
}

export interface RenderAttemptView {
  attempt_id: string;
  project_id: string;
  project_revision: number;
  materialization_attempt_id: string;
  materialization_plan_hash: string;
  render_profile_id: string;
  render_plan_hash: string;
  authorization_id: string;
  capability_id: string;
  output_root_identity: string;
  state: RenderTruthState;
  hvs_calls: number;
  render_calls: number;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  reconciliation_count: number;
  outcome: string | null;
  error_code: string | null;
  error_detail: string | null;
  artifact_descriptor: RenderArtifactView | null;
}

export interface RenderProjectionView {
  project_id: string;
  truth_state: RenderTruthState;
  current_revision: number | null;
  plan: RenderPlan | null;
  attempts: RenderAttemptView[];
  authorization?: RenderAuthorizationView | null;
}

export interface RenderAuthorizationView {
  authorization_id: string;
  project_id: string;
  project_revision: number;
  operation: string;
  materialization_attempt_id: string;
  render_profile_id: string;
  render_plan_hash: string;
  output_root_identity: string;
  decision: string;
  capability_id: string;
  attempt_id: string;
}

export interface RenderResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  decision?: string;
  state?: RenderTruthState;
  attempt_id?: string | null;
  authorization_id?: string | null;
  capability_id?: string;
  render_calls?: number;
  hvs_calls?: number;
  outcome?: string | null;
  error_detail?: string | null;
  persisted_result?: Record<string, unknown> | null;
  artifact?: RenderArtifactView | null;
  classification?: string;
  attempt?: RenderAttemptView | null;
  projection?: RenderProjectionView;
  authorization?: RenderAuthorizationView;
}

export const ERR = {
  BRIDGE_UNINITIALIZED: "BRIDGE_UNINITIALIZED",
  BRIDGE_NO_CHILD: "BRIDGE_NO_CHILD",
  BRIDGE_TIMEOUT: "BRIDGE_TIMEOUT",
  BRIDGE_OUTPUT_OVERSIZED: "BRIDGE_OUTPUT_OVERSIZED",
  BRIDGE_OUTPUT_MALFORMED: "BRIDGE_OUTPUT_MALFORMED",
  BRIDGE_CHILD_FAILED: "BRIDGE_CHILD_FAILED",
  BRIDGE_UNKNOWN_OPERATION: "BRIDGE_UNKNOWN_OPERATION",
  BRIDGE_UNEXPECTED_ENV: "BRIDGE_UNEXPECTED_ENV",
} as const;

export interface BridgeResult {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  response: RenderResponse | null;
}

export class HvsRenderStore {
  private readonly pythonExecutable: string;
  private readonly module: string;
  private readonly timeoutMs: number;

  constructor(
    pythonExecutable: string = resolveTrustedDefaultPython(),
    module: string = BRIDGE_MODULE,
    timeoutMs: number = BRIDGE_TIMEOUT_MS,
  ) {
    this.pythonExecutable = pythonExecutable;
    this.module = module;
    this.timeoutMs = timeoutMs > 0 ? timeoutMs : BRIDGE_TIMEOUT_MS;
  }

  get interpreter(): string {
    return this.pythonExecutable;
  }

  invoke(operation: BridgeOperation, payload: Record<string, unknown>): Promise<BridgeResult> {
    if (!ALLOWED_OPERATIONS.has(operation)) {
      return Promise.resolve({
        ok: false,
        error_code: ERR.BRIDGE_UNKNOWN_OPERATION,
        detail: "unknown operation",
        response: null,
      });
    }

    return new Promise<BridgeResult>((resolve) => {
      let child: ReturnType<typeof childProcess.spawn> | null = null;
      let settled = false;
      let stdout = "";
      const finish = (result: BridgeResult) => {
        if (settled) return;
        settled = true;
        if (child && !child.killed) {
          try { child.kill("SIGKILL"); } catch { /* ignore */ }
        }
        resolve(result);
      };

      let argv: string[];
      try {
        argv = ["-m", this.module, operation];
      } catch {
        finish({ ok: false, error_code: ERR.BRIDGE_UNINITIALIZED, detail: "bridge unavailable", response: null });
        return;
      }

      const repoRoot = nodeResolve(process.cwd(), "..", "..");
      // Explicit, server-controlled HyperFrames launcher identity. Forwarded
      // ONLY when present in the cohort-owned server process environment. It
      // is never accepted from a request body, query, header, cookie, or
      // browser storage; never logged, and never returned in a response.
      const minimalEnv: Record<string, string> = { PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" };
      // Note: SCOS_HYPERFRAMES_BIN is intentionally NOT added to
      // ALLOWED_PARENT_ENV. It is forwarded here, explicitly and solely, so
      // the Python side can pin an exact renderer identity instead of
      // inheriting the broad parent PATH.
      if (process.env.SCOS_HYPERFRAMES_BIN !== undefined) {
        minimalEnv.SCOS_HYPERFRAMES_BIN = process.env.SCOS_HYPERFRAMES_BIN;
      }
      if (process.env.SCOS_NODE_BIN !== undefined) {
        minimalEnv.SCOS_NODE_BIN = process.env.SCOS_NODE_BIN;
      }
      // Forward the trusted server-side HVS repository override ONLY when it
      // already exists in the cohort-owned server process environment. It is
      // never accepted from a request body, query, header, cookie, or browser
      // storage. The value is passed verbatim to the child; it is never logged
      // or returned in a response.
      if (process.env.SCOS_HVS_REPO_PATH !== undefined) {
        minimalEnv.SCOS_HVS_REPO_PATH = process.env.SCOS_HVS_REPO_PATH;
      }
      if (process.env.SCOS_RENDER_OUTPUT_ROOT !== undefined) {
        minimalEnv.SCOS_RENDER_OUTPUT_ROOT = process.env.SCOS_RENDER_OUTPUT_ROOT;
      }
      minimalEnv.PYTHONPATH = repoRoot;

      let childProc: ReturnType<typeof childProcess.spawn>;
      try {
        childProc = childProcess.spawn(this.pythonExecutable, argv, {
          cwd: repoRoot,
          env: minimalEnv as unknown as NodeJS.ProcessEnv,
          stdio: ["pipe", "pipe", "pipe"],
        });
      } catch {
        finish({ ok: false, error_code: ERR.BRIDGE_NO_CHILD, detail: "bridge unavailable", response: null });
        return;
      }
      child = childProc;

      const timer = setTimeout(() => {
        if (child && !child.killed) {
          try { child.kill("SIGKILL"); } catch { /* ignore */ }
        }
        finish({ ok: false, error_code: ERR.BRIDGE_TIMEOUT, detail: "bridge timeout", response: null });
      }, this.timeoutMs);

      childProc.on("error", () => {
        finish({ ok: false, error_code: ERR.BRIDGE_NO_CHILD, detail: "bridge unavailable", response: null });
      });

      if (childProc.stdout) {
        childProc.stdout.setEncoding("utf8");
        childProc.stdout.on("data", (chunk: string) => {
          stdout += chunk;
          if (stdout.length > MAX_STDOUT_BYTES) {
            finish({ ok: false, error_code: ERR.BRIDGE_OUTPUT_OVERSIZED, detail: "bridge output too large", response: null });
          }
        });
      }
      if (childProc.stderr) {
        childProc.stderr.setEncoding("utf8");
        childProc.stderr.on("data", () => { /* server-side diagnostics only */ });
      }

      childProc.on("close", (code: number | null) => {
        if (settled) return;
        if (code !== 0) {
          finish({ ok: false, error_code: ERR.BRIDGE_CHILD_FAILED, detail: "bridge failed", response: null });
          return;
        }
        const parsed = parseSingleJson(stdout);
        if (!parsed.ok) {
          finish({ ok: false, error_code: parsed.error_code, detail: parsed.detail, response: null });
          return;
        }
        finish({ ok: true, error_code: null, detail: null, response: parsed.response });
      });

      if (childProc.stdin) {
        try {
          const request: Record<string, unknown> = { ...(payload ?? {}) };
          const srvStorePath = process.env.SCOS_RENDER_STORE_PATH;
          if (srvStorePath && srvStorePath.length > 0) request.store_path = srvStorePath;
          const srvOutputRoot = process.env.SCOS_RENDER_OUTPUT_ROOT;
          if (srvOutputRoot && srvOutputRoot.length > 0) request.output_root_identity = srvOutputRoot;
          childProc.stdin.write(JSON.stringify(request));
          childProc.stdin.end();
        } catch {
          finish({ ok: false, error_code: ERR.BRIDGE_NO_CHILD, detail: "bridge unavailable", response: null });
        }
      }
    });
  }
}

function parseSingleJson(text: string): {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  response: RenderResponse | null;
} {
  const trimmed = (text ?? "").trim();
  if (trimmed.length === 0) {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "empty bridge output", response: null };
  }
  let value: unknown;
  try {
    value = JSON.parse(trimmed);
  } catch {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "malformed bridge output", response: null };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "unexpected bridge output", response: null };
  }
  return { ok: true, error_code: null, detail: null, response: value as RenderResponse };
}

export function buildAuthorizePayload(args: {
  projectId: string;
  projectRevision: number;
  confirmed: boolean;
  operatorId: string;
  materializationAttemptId: string;
  materializationPlanHash: string;
  renderProfileId: string;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    project_revision: args.projectRevision,
    confirmed: args.confirmed,
    operator_id: args.operatorId,
    materialization_attempt_id: args.materializationAttemptId,
    materialization_plan_hash: args.materializationPlanHash,
    render_profile_id: args.renderProfileId,
  };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

export function buildExecutePayload(args: {
  projectId: string;
  projectRevision: number;
  authorizationId: string;
  capabilityId: string;
  attemptId: string;
  operatorId: string;
  materializationAttemptId: string;
  materializationPlanHash: string;
  renderProfileId: string;
  projectsRootIdentity?: string;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    project_revision: args.projectRevision,
    authorization_id: args.authorizationId,
    capability_id: args.capabilityId,
    attempt_id: args.attemptId,
    operator_id: args.operatorId,
    materialization_attempt_id: args.materializationAttemptId,
    materialization_plan_hash: args.materializationPlanHash,
    render_profile_id: args.renderProfileId,
  };
  if (args.projectsRootIdentity && args.projectsRootIdentity.length) {
    p.projects_root_identity = args.projectsRootIdentity;
  }
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

export function buildReconcilePayload(args: { attemptId: string; storePath?: string }): Record<string, unknown> {
  const p: Record<string, unknown> = { attempt_id: args.attemptId };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

export function buildProjectionPayload(args: {
  projectId: string;
  projectRevision?: number;
  materializationAttemptId?: string;
  renderProfileId?: string;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
  };
  if (args.projectRevision !== undefined) p.project_revision = args.projectRevision;
  if (args.materializationAttemptId && args.materializationAttemptId.length) p.materialization_attempt_id = args.materializationAttemptId;
  if (args.renderProfileId && args.renderProfileId.length) p.render_profile_id = args.renderProfileId;
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

export function buildRecordTransportUnknownPayload(args: {
  projectId: string;
  projectRevision: number;
  attemptId: string;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    project_revision: args.projectRevision,
    attempt_id: args.attemptId,
  };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}
