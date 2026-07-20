/**
 * Cohort 10G — thin, bounded transport to the Python golden-render authority.
 *
 * NO authority here: no authorization, no render decision, no persistence.
 * The authoritative boundary lives in
 *   scos/control_center/hvs_golden_render_service.py
 *   scos/control_center/hvs_golden_render_cli.py   (bridge entrypoint)
 * reached ONLY through: python -m scos.control_center.hvs_golden_render_cli <op>
 *
 * Transport contract (same as hvs-render-store.ts): argv array, never shell;
 * canonical interpreter from trusted server config; JSON on stdin; exactly one
 * JSON on stdout; malformed/oversized => failure; raw stderr NEVER returned;
 * bounded timeout kills only the owned child; no automatic retry; only an
 * explicit minimal environment is forwarded; SCOS_HYPERFRAMES_BIN is forwarded
 * verbatim when present (never browser-supplied).
 */

import * as childProcess from "node:child_process";
import { resolve as nodeResolve, delimiter as os_pathsep } from "node:path";
import {
  type GoldenRenderProfile,
  type GoldenRenderOperation,
  type GoldenRenderRequest,
  buildExecutePayload,
  serverResolvedScope,
  validateGoldenRenderRequest,
} from "./golden-render-contract";

export {
  type GoldenRenderProfile,
  type GoldenRenderOperation,
  type GoldenRenderRequest,
  buildExecutePayload,
  serverResolvedScope,
  validateGoldenRenderRequest,
};

function resolveTrustedDefaultPython(): string {
  return process.env.SCOS_PYTHON_INTERPRETER && process.env.SCOS_PYTHON_INTERPRETER.length > 0
    ? process.env.SCOS_PYTHON_INTERPRETER
    : nodeResolve(process.cwd(), "..", "..", ".venv", "Scripts", "python.exe");
}

const BRIDGE_MODULE_DEFAULT = "scos.control_center.hvs_golden_render_cli";

function resolveBridgeModule(): string {
  // Resolved at call time (not import time) so isolated tests can override
  // it via the trusted, server-controlled SCOS_BRIDGE_MODULE env without
  // being clobbered by module-load-order. Never browser-supplied.
  return process.env.SCOS_BRIDGE_MODULE || BRIDGE_MODULE_DEFAULT;
}

const ALLOWED_OPERATIONS: ReadonlySet<GoldenRenderOperation> = new Set<GoldenRenderOperation>([
  "projection",
  "execute",
  "reconcile",
]);

const MAX_STDOUT_BYTES = 1_048_576;
const BRIDGE_TIMEOUT_MS = 300_000; // 5 min (real renders are slow)

export interface GoldenRenderResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  state?: string;
  attempt_id?: string | null;
  artifact_id?: string | null;
  artifact_checksum?: string | null;
  render_calls?: number;
  hvs_calls?: number;
  qa_overall_state?: string | null;
  qa_report_id?: string | null;
  qa_failure_codes?: string[];
  attempt?: Record<string, unknown> | null;
  qa_report?: Record<string, unknown> | null;
  attempts?: Record<string, unknown>[];
  supported_profiles?: string[];
  mutated?: boolean;
}

export const ERR = {
  BRIDGE_UNINITIALIZED: "BRIDGE_UNINITIALIZED",
  BRIDGE_NO_CHILD: "BRIDGE_NO_CHILD",
  BRIDGE_TIMEOUT: "BRIDGE_TIMEOUT",
  BRIDGE_OUTPUT_OVERSIZED: "BRIDGE_OUTPUT_OVERSIZED",
  BRIDGE_OUTPUT_MALFORMED: "BRIDGE_OUTPUT_MALFORMED",
  BRIDGE_CHILD_FAILED: "BRIDGE_CHILD_FAILED",
  BRIDGE_UNKNOWN_OPERATION: "BRIDGE_UNKNOWN_OPERATION",
} as const;

export interface BridgeResult {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  response: GoldenRenderResponse | null;
}

export class GoldenRenderStore {
  private readonly pythonExecutable: string;
  private readonly module: string;
  private readonly timeoutMs: number;

  constructor(
    pythonExecutable: string = resolveTrustedDefaultPython(),
    module: string = BRIDGE_MODULE_DEFAULT,
    timeoutMs: number = BRIDGE_TIMEOUT_MS,
  ) {
    this.pythonExecutable = pythonExecutable;
    this.module = module;
    this.timeoutMs = timeoutMs > 0 ? timeoutMs : BRIDGE_TIMEOUT_MS;
  }

  get interpreter(): string {
    return this.pythonExecutable;
  }

  invoke(operation: GoldenRenderOperation, payload: Record<string, unknown>): Promise<BridgeResult> {
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
        argv = ["-m", resolveBridgeModule(), operation];
      } catch {
        finish({ ok: false, error_code: ERR.BRIDGE_UNINITIALIZED, detail: "bridge unavailable", response: null });
        return;
      }

      const repoRoot = nodeResolve(process.cwd(), "..", "..");
      const minimalEnv: Record<string, string> = { PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" };
      if (process.env.SCOS_HYPERFRAMES_BIN !== undefined) {
        minimalEnv.SCOS_HYPERFRAMES_BIN = process.env.SCOS_HYPERFRAMES_BIN;
      }
      if (process.env.SCOS_HVS_REPO_PATH !== undefined) {
        minimalEnv.SCOS_HVS_REPO_PATH = process.env.SCOS_HVS_REPO_PATH;
      }
      if (process.env.SCOS_GOLDEN_RENDER_STORE_PATH !== undefined) {
        minimalEnv.SCOS_GOLDEN_RENDER_STORE_PATH = process.env.SCOS_GOLDEN_RENDER_STORE_PATH;
      }
      if (process.env.SCOS_PYTHON_INTERPRETER !== undefined) {
        minimalEnv.SCOS_PYTHON_INTERPRETER = process.env.SCOS_PYTHON_INTERPRETER;
      }
      if (process.env.SCOS_RENDER_OUTPUT_ROOT !== undefined) {
        minimalEnv.SCOS_RENDER_OUTPUT_ROOT = process.env.SCOS_RENDER_OUTPUT_ROOT;
      }
      // Optional, server-controlled extra import path prepended ahead of the
      // repo root. Used only by isolated tests to inject a deterministic stub
      // bridge module; never browser-supplied, never logged.
      if (process.env.SCOS_BRIDGE_EXTRA_PATH !== undefined) {
        minimalEnv.PYTHONPATH = process.env.SCOS_BRIDGE_EXTRA_PATH + os_pathsep + repoRoot;
      } else {
        minimalEnv.PYTHONPATH = repoRoot;
      }

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
          const srvStore = process.env.SCOS_GOLDEN_RENDER_STORE_PATH;
          if (srvStore && srvStore.length) request.store_path = srvStore;
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
  response: GoldenRenderResponse | null;
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
  return { ok: true, error_code: null, detail: null, response: value as GoldenRenderResponse };
}

export function buildProjectionPayload(args: {
  projectId: string;
  hvsProjectId: string;
  profileId?: GoldenRenderProfile;
  storePath?: string;
}): Record<string, unknown> {
  const p: Record<string, unknown> = {
    project_id: args.projectId,
    hvs_project_id: args.hvsProjectId,
  };
  if (args.profileId && args.profileId.length) p.profile_id = args.profileId;
  if (args.storePath && args.storePath.length) p.store_path = args.storePath;
  return p;
}
