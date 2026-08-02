/** Server-only bridge for canonical paid-pilot project creation (§6.E/§6.F bridge).

 *  The browser never supplies a filesystem path. All roots, stores, the packet
 *  path and the contracts directory are resolved server-side from trusted
 *  environment variables. This bridge only forwards the operator-controlled
 *  idempotency key (server-generated, not browser-controlled).
 */

import * as childProcess from "node:child_process";
import * as fs from "node:fs";
import { dirname, join, resolve } from "node:path";

const MODULE = "scos.control_center.hvs_pilot_cli";
const MAX = 2_097_152;

function repoRoot(): string {
  const r = process.env.SCOS_REPO_ROOT;
  if (r) return r;
  let c = process.cwd();
  for (let i = 0; i < 4; i++) {
    if (fs.existsSync(join(c, "scos", "control_center"))) return c;
    c = dirname(c);
  }
  return resolve(process.cwd(), "..", "..");
}

function resolvePython(): string | null {
  const explicit = process.env.SCOS_PYTHON_INTERPRETER;
  if (explicit && explicit.length > 0) {
    return fs.existsSync(explicit) ? explicit : null;
  }
  const root = repoRoot();
  const candidates = [
    resolve(root, ".venv", "Scripts", "python.exe"),
    resolve(root, ".venv", "bin", "python"),
    resolve(root, "..", "super-creator-os", ".venv", "Scripts", "python.exe"),
    resolve(root, "..", "super-creator-os", ".venv", "bin", "python"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

export interface CreateResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  canonical_internal_project_id?: string;
  pilot_safe_id?: string;
  project_safe_id?: string;
  external_project_ref?: string;
  admission_packet_sha256?: string;
  replay?: boolean;
  materialization?: Record<string, unknown>;
  next_safe_action?: string;
}

export function invokeCreateCanonical(operation: string, payload: Record<string, unknown>): Promise<CreateResponse> {
  return new Promise((resolveOut) => {
    const root = repoRoot();
    const python = resolvePython();
    if (!python) {
      resolveOut({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "canonical creation authority unavailable" });
      return;
    }
    const child = childProcess.spawn(python, ["-m", MODULE, operation], {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" },
      windowsHide: true,
    });
    let out = "";
    let done = false;
    const finish = (r: CreateResponse) => {
      if (done) return;
      done = true;
      resolveOut(r);
    };
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch { /* noop */ }
      finish({ ok: false, error_code: "BRIDGE_TIMEOUT", detail: "canonical creation bridge timed out" });
    }, 60000);
    child.stdout.on("data", (b: Buffer) => {
      out += b.toString("utf8");
      if (out.length > MAX) { try { child.kill("SIGKILL"); } catch { /* noop */ } }
    });
    child.on("error", () => {
      clearTimeout(timer);
      finish({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "canonical creation authority unavailable" });
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out.trim() || "{}");
        finish({
          ok: Boolean(parsed.ok),
          error_code: parsed.error_code ?? null,
          detail: parsed.detail ?? null,
          canonical_internal_project_id: parsed.canonical_internal_project_id,
          pilot_safe_id: parsed.pilot_safe_id,
          project_safe_id: parsed.project_safe_id,
          external_project_ref: parsed.external_project_ref,
          admission_packet_sha256: parsed.admission_packet_sha256,
          replay: parsed.replay ?? undefined,
          materialization: parsed.materialization ?? undefined,
          next_safe_action: parsed.next_safe_action ?? undefined,
        });
      } catch {
        finish({ ok: false, error_code: "BRIDGE_MALFORMED_OUTPUT", detail: "canonical creation authority returned malformed output" });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}
