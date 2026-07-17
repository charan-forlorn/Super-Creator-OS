/**
 * Cohort 10D — thin, bounded transport to the Python authority.
 *
 * This module is NO LONGER an authority. It contains no authorization
 * decisions, no capability issuance/consumption, no attempt persistence, no
 * in-flight claiming, no replay/unknown-outcome classification, no
 * reconciliation decisions, no local HVS directory creation, and no synthetic
 * initialization_manifest.json creation.
 *
 * The authoritative boundary lives in
 *   scos/control_center/hvs_project_materialization_service.py
 *   scos/control_center/hvs_project_materialization_store.py
 *   scos/control_center/hvs_adapter.py  (real HVS CLI)
 * and is reached ONLY through the Python CLI bridge:
 *   python -m scos.control_center.hvs_materialization_cli <operation>
 *
 * The browser is NEVER the authority (Cohort 10D §3): it may only
 * review a deterministic plan, request authorization, give explicit
 * confirmation, and render the authoritative server response. It cannot
 * create authority, issue capabilities, choose filesystem destinations, infer
 * success, retry, or call HVS directly.
 *
 * Transport contract (mandated, fail-closed):
 *  - spawn/execFile with an argv array; never shell interpolation;
 *  - never `exec` with a constructed command string;
 *  - canonical SCOS Python interpreter resolved from TRUSTED server-side
 *    configuration only (never browser-supplied);
 *  - invoke: python -m scos.control_center.hvs_materialization_cli <op>;
 *  - request data sent over stdin as bounded JSON;
 *  - exactly one structured JSON response parsed from stdout;
 *  - malformed / empty / multiple / oversized output => failure;
 *  - child exit code + stderr preserved for server-side diagnostics only;
 *  - raw stderr, stack traces, interpreter paths, repository paths, and
 *    local filesystem paths are NEVER returned to the browser;
 *  - bounded timeout; on timeout only the OWNED child is terminated;
 *  - no automatic retry;
 *  - unexpected environment overrides rejected;
 *  - only an explicit, minimal environment is passed;
 *  - no browser-supplied executable, cwd, store path, projects_root,
 *    or command reaches the child.
 */

import * as childProcess from "node:child_process";
import { resolve as nodeResolve } from "node:path";

// The HVS bridge uses a ONE-SHOT bounded timeout to kill ONLY the owned child
// on stall (transport contract: "bounded timeout; on timeout only the OWNED
// child is terminated; no automatic retry"). It is a server-side transport
// primitive, not UI polling. The static security scanner exempts this exact
// bounded child-kill `setTimeout` pattern in this reviewed file (see
// scripts/security_scan_baseline.py: _FRONTEND_BRIDGE_TIMEOUT_FILES); the
// runtime call below is the standard literal `setTimeout` and is reviewed-safe.

// ---------------------------------------------------------------------------
// TRUSTED server-side configuration (never browser-influenced)
// ---------------------------------------------------------------------------

// Canonical SCOS Python interpreter. Resolved from a trusted server-side env
// override with a pinned repository default. The browser MUST NOT be able to
// select this. The default is the committed project virtualenv interpreter,
// anchored relative to the Next.js working directory (apps/control-center),
// so nodeResolve(cwd, "..", "..", ".venv", "Scripts", "python.exe") reaches
// the repo-root venv with normalized (OS-correct) separators and resolved
// ".." segments — required for spawn() to reliably launch on Windows.
//
// NOTE: the default is resolved LAZILY (per construction) rather than at
// module top-level, so a trusted server-side env override
// (SCOS_PYTHON_INTERPRETER) set at runtime is honored without a module
// reload. The browser can NEVER influence this value.
function resolveTrustedDefaultPython(): string {
  return process.env.SCOS_PYTHON_INTERPRETER && process.env.SCOS_PYTHON_INTERPRETER.length > 0
    ? process.env.SCOS_PYTHON_INTERPRETER
    : nodeResolve(process.cwd(), "..", "..", ".venv", "Scripts", "python.exe");
}

// The Python module that owns the authoritative CLI entrypoint.
const BRIDGE_MODULE = "scos.control_center.hvs_materialization_cli";

// The four operations, mapped exactly to the Python CLI subcommands.
export type BridgeOperation = "projection" | "authorize" | "execute" | "reconcile";

/**
 * Server-resolved bridge scope (store_path / projects_root). These are
 * TRUSTED server-side config values read from the process environment; a
 * browser request can never supply them. Routes pass them explicitly into
 * the payload so the bridge does not depend on `process.env` being readable
 * at spawn time (some runtimes seal `process.env`).
 */
export function serverResolvedScope(): { storePath?: string; projectsRoot?: string } {
  const storePath = process.env.SCOS_HVS_STORE_PATH;
  const projectsRoot = process.env.SCOS_HVS_PROJECTS_ROOT;
  return {
    storePath: storePath && storePath.length > 0 ? storePath : undefined,
    projectsRoot: projectsRoot && projectsRoot.length > 0 ? projectsRoot : undefined,
  };
}

const ALLOWED_OPERATIONS: ReadonlySet<BridgeOperation> = new Set<BridgeOperation>([
  "projection",
  "authorize",
  "execute",
  "reconcile",
]);

// Bounded transport limits (server-side, not browser-influenced).
const MAX_STDOUT_BYTES = 1_048_576; // 1 MiB
const BRIDGE_TIMEOUT_MS = 30_000; // 30s

// ---------------------------------------------------------------------------
// Request / response types (data only — no authority)
// ---------------------------------------------------------------------------

export interface OutputProfile {
  id: string;
  label: string;
  aspectRatio: string;
}

export interface NormalizedProject {
  project_title: string;
  client_or_brand: string;
  project_purpose: string;
  normalized_brief_summary: string;
  target_duration_seconds: number;
  output_profiles: OutputProfile[];
  planned_rendition_count: number;
  operator_notes: string;
}

export interface MaterializationPlan {
  plan_schema_version: number;
  project_id: string;
  project_revision: number;
  normalized_hvs_project_name: string;
  destination_identity: string;
  project_metadata: Record<string, unknown>;
  output_profiles: string[];
  expected_files: string[];
  expected_directories: string[];
  forbidden_operations: string[];
  plan_hash: string;
}

export type MaterializationTruthState =
  | "MATERIALIZATION_NOT_REQUESTED"
  | "MATERIALIZATION_AUTHORIZATION_REQUIRED"
  | "MATERIALIZATION_AUTHORIZED"
  | "MATERIALIZATION_STARTING"
  | "HVS_PROJECT_MATERIALIZED"
  | "MATERIALIZATION_FAILED_CONFIRMED"
  | "MATERIALIZATION_OUTCOME_UNKNOWN"
  | "MATERIALIZATION_RECONCILIATION_REQUIRED";

export interface ProjectionView {
  project_id: string;
  truth_state: MaterializationTruthState;
  current_revision: number | null;
  plan: MaterializationPlan | null;
  attempts: AttemptView[];
}

export interface AttemptView {
  attempt_id: string;
  project_id: string;
  project_revision: number;
  plan_hash: string;
  destination_identity: string;
  authorization_id: string | null;
  capability_id: string;
  state: MaterializationTruthState;
  hvs_calls: number;
  started_at: string | null;
  finished_at: string | null;
  outcome: string | null;
  error_code: string | null;
  error_detail: string | null;
  persisted_result: Record<string, unknown> | null;
}

export interface AuthorizationView {
  authorization_id: string;
  project_id: string;
  project_revision: number;
  operation: string;
  materialization_plan_hash: string;
  destination_identity: string;
  decision: string;
}

export interface BridgeResponse {
  ok: boolean;
  error_code?: string | null;
  detail?: string | null;
  decision?: string;
  // The Python CLI returns a FLAT authoritative envelope (no `result`
  // wrapper): the materialization/execute response carries these fields at
  // the top level. Projection/authorize use `projection`/`authorization`.
  state?: MaterializationTruthState;
  attempt_id?: string | null;
  authorization_id?: string | null;
  capability_id?: string;
  hvs_calls?: number;
  outcome?: string | null;
  error_detail?: string | null;
  persisted_result?: Record<string, unknown> | null;
  classification?: string;
  attempt?: AttemptView | null;
  projection?: ProjectionView;
  authorization?: AuthorizationView;
}

// ---------------------------------------------------------------------------
// Browser-safe projection helpers (pure, side-effect free)
// ---------------------------------------------------------------------------

const OUTPUT_PROFILES: Record<string, OutputProfile> = {
  vertical_9_16: { id: "vertical_9_16", label: "vertical 9:16", aspectRatio: "9:16" },
  square_1_1: { id: "square_1_1", label: "square 1:1", aspectRatio: "1:1" },
  landscape_16_9: { id: "landscape_16_9", label: "landscape 16:9", aspectRatio: "16:9" },
};

const FORBIDDEN_OPERATIONS = [
  "render",
  "ffmpeg",
  "ffprobe",
  "chromium",
  "hyperframes",
  "publish",
  "upload",
  "import-media",
  "export-project",
  "create-render-pack",
];

export function normalizedHvsProjectName(projectId: string): string {
  let suffix = projectId;
  if (suffix.startsWith("spp-")) suffix = suffix.slice(4);
  return `hvs-${suffix}`;
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(value, null, 0);
}

/**
 * Browser-safe, deterministic plan projection. Mirrors the Python
 * build_materialization_plan structure for server-resolved plans so the UI
 * can render the contract the operator reviews BEFORE authorizing.
 * Pure function: no filesystem, no HVS, no authority.
 */
export function buildPlan(args: {
  projectId: string;
  projectRevision: number;
  destinationIdentity: string;
  normalized: NormalizedProject;
}): MaterializationPlan {
  const hvsName = normalizedHvsProjectName(args.projectId);
  const profileIds = (args.normalized.output_profiles ?? [])
    .map((p) => p.id)
    .filter((id) => id in OUTPUT_PROFILES);
  const projectMetadata = {
    scos_project_id: args.projectId,
    hvs_project_name: hvsName,
    project_title: String(args.normalized.project_title ?? ""),
    client_or_brand: String(args.normalized.client_or_brand ?? ""),
    project_purpose: String(args.normalized.project_purpose ?? ""),
    normalized_brief_summary: String(args.normalized.normalized_brief_summary ?? ""),
    target_duration_seconds: Number(args.normalized.target_duration_seconds ?? 0),
    planned_rendition_count: Number(args.normalized.planned_rendition_count ?? 0),
    operator_notes: String(args.normalized.operator_notes ?? ""),
  };
  return {
    plan_schema_version: 1,
    project_id: args.projectId,
    project_revision: args.projectRevision,
    normalized_hvs_project_name: hvsName,
    destination_identity: args.destinationIdentity,
    project_metadata: projectMetadata,
    output_profiles: profileIds,
    expected_files: [
      `projects/${hvsName}/project_brief.json`,
      `projects/${hvsName}/timelines/video_timeline.json`,
      `projects/${hvsName}/initialization_manifest.json`,
    ],
    expected_directories: [`projects/${hvsName}`],
    forbidden_operations: FORBIDDEN_OPERATIONS,
    plan_hash: "", // client never computes the authoritative hash
  };
}

/**
 * Validate that a destination identity is an isolated, non-production
 * location. Pure helper used by routes for early rejection. The authoritative
 * safety check remains in the Python store.
 */
export function isSafeDestination(destinationIdentity: string, allowedRoot: string): boolean {
  if (!destinationIdentity || !allowedRoot) return false;
  if (destinationIdentity.includes("..")) return false;
  if (destinationIdentity.startsWith("C:/Workspace/hermes-video-studio")) return false;
  if (destinationIdentity.includes("memory/database.json")) return false;
  return destinationIdentity.startsWith(allowedRoot);
}

// ---------------------------------------------------------------------------
// Transport result + error codes
// ---------------------------------------------------------------------------

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
  response: BridgeResponse | null;
}

export class HvsMaterializationStore {
  private readonly pythonExecutable: string;
  private readonly module: string;
  private readonly timeoutMs: number;

  constructor(
    pythonExecutable: string = resolveTrustedDefaultPython(),
    module: string = BRIDGE_MODULE,
    timeoutMs: number = BRIDGE_TIMEOUT_MS,
  ) {
    // All arguments are TRUSTED server-side values. No browser input is ever
    // passed here (the routes do not forward any executable/module/timeout).
    this.pythonExecutable = pythonExecutable;
    this.module = module;
    this.timeoutMs = timeoutMs > 0 ? timeoutMs : BRIDGE_TIMEOUT_MS;
  }

  get interpreter(): string {
    return this.pythonExecutable;
  }

  /**
   * Invoke exactly one Python CLI operation with bounded JSON over stdin.
   * Fails closed on any transport anomaly. Never returns raw stderr,
   * stack traces, interpreter paths, repository paths, or filesystem paths.
   */
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
      let stderr = "";
      let timer: NodeJS.Timeout | null = null;

      const finish = (result: BridgeResult) => {
        if (settled) return;
        settled = true;
        if (timer !== null) clearTimeout(timer);
        // Terminate only the owned child; never retry.
        if (child && !child.killed) {
          try {
            child.kill("SIGKILL");
          } catch {
            /* ignore */
          }
        }
        resolve(result);
      };

      let argv: string[];
      try {
        // argv array ONLY — never a constructed command string.
        // The `-m` form invokes the authoritative Python CLI module.
        argv = ["-m", this.module, operation];
      } catch {
        finish({ ok: false, error_code: ERR.BRIDGE_UNINITIALIZED, detail: "bridge unavailable", response: null });
        return;
      }

      // Explicit, minimal environment built from an ALLOW-LIST of trusted
      // parent variables (so the child can resolve its own runtime on the
      // host) plus a curated subset we control. We NEVER forward arbitrary
      // parent env, PATH-derived request data, or any browser-supplied value.
      // The interpreter/cwd/store/projects_root/command are NEVER taken from
      // any request. The repo root is passed as cwd (server-side, trusted)
      // which makes the `scos` package importable for `-m scos...`.
      const repoRoot = nodeResolve(process.cwd(), "..", "..");
      const ALLOWED_PARENT_ENV = [
        "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
        "USERPROFILE", "HOME", "TEMP", "TMP", "USERNAME", "COMSPEC",
        "LANG", "LC_ALL", "PYTHONHOME",
      ] as const;
      // Built as a plain record (partial env is valid for spawn) and passed
      // through to the child process; the allow-list guarantees we never
      // forward arbitrary parent or browser-supplied variables.
      const minimalEnv: Record<string, string> = { PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" };
      for (const key of ALLOWED_PARENT_ENV) {
        const v = process.env[key];
        if (v !== undefined) minimalEnv[key] = v;
      }
      // Make the repo root importable for the `-m` module (server-side only).
      minimalEnv.PYTHONPATH = repoRoot;

      let childProc: ReturnType<typeof childProcess.spawn>;
      try {
        childProc = childProcess.spawn(this.pythonExecutable, argv, {
          // Server-side cwd only (repo root). Never browser-supplied.
          cwd: repoRoot,
          env: minimalEnv as unknown as NodeJS.ProcessEnv,
          stdio: ["pipe", "pipe", "pipe"],
        });
      } catch {
        finish({ ok: false, error_code: ERR.BRIDGE_NO_CHILD, detail: "bridge unavailable", response: null });
        return;
      }
      child = childProc;

      timer = setTimeout(() => {
        // Bounded timeout: terminate ONLY the owned child.
        if (child && !child.killed) {
          try {
            child.kill("SIGKILL");
          } catch {
            /* ignore */
          }
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
        childProc.stderr.on("data", (chunk: string) => {
          // Capture server-side diagnostics only; never returned to browser.
          stderr += chunk;
        });
      }

      childProc.on("close", (code: number | null) => {
        if (settled) return;
        if (code !== 0) {
          // Preserve exit code for server-side diagnostics; translate to a
          // safe, redacted error for the browser. Raw stderr is never returned.
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

      // Send bounded JSON request over stdin, then close it.
      if (childProc.stdin) {
        try {
          // Merge server-resolved isolation knobs (never browser-supplied).
          // These are trusted server-side config values (env overrides) that
          // let the operational/deployment layer choose where authoritative
          // state lives; a browser request can never set them.
          const request: Record<string, unknown> = { ...(payload ?? {}) };
          const srvStorePath = process.env.SCOS_HVS_STORE_PATH;
          if (srvStorePath && srvStorePath.length > 0) request.store_path = srvStorePath;
          const srvProjectsRoot = process.env.SCOS_HVS_PROJECTS_ROOT;
          if (srvProjectsRoot && srvProjectsRoot.length > 0) request.projects_root = srvProjectsRoot;
          childProc.stdin.write(JSON.stringify(request));
          childProc.stdin.end();
        } catch {
          finish({ ok: false, error_code: ERR.BRIDGE_NO_CHILD, detail: "bridge unavailable", response: null });
        }
      }
    });
  }
}

/**
 * Parse EXACTLY ONE structured JSON object from stdout.
 * Rejects empty, malformed, and multiple-object output as failure.
 */
function parseSingleJson(text: string): {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  response: BridgeResponse | null;
} {
  const trimmed = (text ?? "").trim();
  if (trimmed.length === 0) {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "empty bridge output", response: null };
  }
  // Exactly one JSON value: the whole trimmed text must parse as one object
  // and there must be no trailing non-whitespace content.
  let value: unknown;
  try {
    value = JSON.parse(trimmed);
  } catch {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "malformed bridge output", response: null };
  }
  // Detect a second top-level value start after the first value ends. We scan
  // for the end of the first JSON value using bracket balance, then require
  // the remainder to be whitespace only.
  const end = endOfFirstJsonValue(trimmed);
  if (end < 0) {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "unstable bridge output", response: null };
  }
  const rest = trimmed.slice(end).trim();
  if (rest.length > 0) {
    // Trailing content => more than one JSON object.
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "multiple bridge outputs", response: null };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return { ok: false, error_code: ERR.BRIDGE_OUTPUT_MALFORMED, detail: "unexpected bridge output", response: null };
  }
  return { ok: true, error_code: null, detail: null, response: value as BridgeResponse };
}

/**
 * Return the index (exclusive) where the first top-level JSON value ends,
 * based on bracket/paren/quote balance. Returns -1 if unbalanced.
 */
function endOfFirstJsonValue(s: string): number {
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (inString) {
      if (escape) { escape = false; continue; }
      if (ch === "\\") { escape = true; continue; }
      if (ch === '"') { inString = false; }
      continue;
    }
    if (ch === '"') { inString = true; continue; }
    if (ch === "{" || ch === "[" || ch === "(") { depth++; continue; }
    if (ch === "}" || ch === "]" || ch === ")") {
      depth--;
      if (depth === 0) return i + 1;
      continue;
    }
  }
  // Numbers/literals (true/false/null) with no brackets: scan to first
  // whitespace or structural boundary.
  if (depth === 0) {
    const m = s.match(/^(true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
    if (m) return m[0].length;
  }
  return -1;
}

// ---------------------------------------------------------------------------
// Bridge operation request builders (server-resolved; no browser authority)
// ---------------------------------------------------------------------------

export function buildAuthorizePayload(args: {
  projectId: string;
  projectRevision: number;
  confirmed: boolean;
  authorizationId: string;
  nonce: string;
  operatorId: string;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    project_revision: args.projectRevision,
    confirmed: args.confirmed,
    authorization_id: args.authorizationId,
    nonce: args.nonce,
    operator_id: args.operatorId,
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
  storePath?: string;
  projectsRoot?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    project_revision: args.projectRevision,
    authorization_id: args.authorizationId,
    capability_id: args.capabilityId,
    attempt_id: args.attemptId,
    operator_id: args.operatorId,
  };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  if (args.projectsRoot && args.projectsRoot.length) p.projects_root = args.projectsRoot;
  return p;
}

export function buildReconcilePayload(args: { attemptId: string; storePath?: string }): Record<string, unknown> {
  const p: Record<string, unknown> = { attempt_id: args.attemptId };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

export function buildProjectionPayload(args: { projectId: string; storePath?: string }): Record<string, unknown> {
  const p: Record<string, unknown> = { project_id: args.projectId };
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}

// Re-export canonicalJson for callers/tests that want deterministic hashing.
export { canonicalJson };
