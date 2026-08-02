/** Server-only bridge for the packet-admission authority (§6.A).

 *  The browser never supplies a filesystem path. The packet path, approved input
 *  root, and all stores are resolved server-side from trusted environment
 *  variables (see scos/control_center/hvs_pilot_roots.py). This bridge only
 *  forwards the operator-supplied expected SHA-256 and an optional server packet
 *  path (itself validated against an allowed root).
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

export interface AdmissionResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  gates?: Array<{ token: string; passed: boolean; reason_code: string; detail: string }>;
  assets?: Array<Record<string, unknown>>;
  projection?: Record<string, unknown>;
}

export function invokeAdmission(operation: string, payload: Record<string, unknown>): Promise<AdmissionResponse> {
  return new Promise((resolveOut) => {
    const root = repoRoot();
    const python = resolvePython();
    if (!python) {
      resolveOut({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "packet admission authority unavailable" });
      return;
    }
    const child = childProcess.spawn(python, ["-m", MODULE, operation], {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" },
      windowsHide: true,
    });
    let out = "";
    let done = false;
    const finish = (r: AdmissionResponse) => {
      if (done) return;
      done = true;
      resolveOut(r);
    };
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      finish({ ok: false, error_code: "BRIDGE_TIMEOUT", detail: "packet admission bridge timed out" });
    }, 60000);
    child.stdout.on("data", (b: Buffer) => {
      out += b.toString("utf8");
      if (out.length > MAX) { try { child.kill("SIGKILL"); } catch {} }
    });
    child.on("error", () => {
      clearTimeout(timer);
      finish({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "packet admission authority unavailable" });
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out.trim() || "{}");
        finish({
          ok: Boolean(parsed.ok),
          error_code: parsed.error_code ?? null,
          detail: parsed.detail ?? null,
          gates: parsed.gates ?? undefined,
          assets: parsed.assets ?? undefined,
          projection: parsed.projection ?? undefined,
        });
      } catch {
        finish({ ok: false, error_code: "BRIDGE_MALFORMED_OUTPUT", detail: "packet admission authority returned malformed output" });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}
