/** Server-only bridge for the pre-render readiness authority (§6.F).

 *  The browser never supplies filesystem paths. All roots are resolved
 *  server-side. This bridge only forwards safe identifiers (project refs / canonical
 *  ids) produced by the server-owned admission + identity flow.
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
  if (explicit && explicit.length > 0) return fs.existsSync(explicit) ? explicit : null;
  const root = repoRoot();
  const candidates = [
    resolve(root, ".venv", "Scripts", "python.exe"),
    resolve(root, ".venv", "bin", "python"),
    resolve(root, "..", "super-creator-os", ".venv", "Scripts", "python.exe"),
    resolve(root, "..", "super-creator-os", ".venv", "bin", "python"),
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

export interface ReadinessResponse {
  ok: boolean;
  state: string;
  error_code: string | null;
  detail: string | null;
  checks?: Array<{ token: string; passed: boolean; reason_code: string; detail: string }>;
  projection?: Record<string, unknown>;
}

export function invokeRenderReadiness(payload: Record<string, unknown>): Promise<ReadinessResponse> {
  return new Promise((resolveOut) => {
    const root = repoRoot();
    const python = resolvePython();
    if (!python) {
      resolveOut({ ok: false, state: "NOT_READY", error_code: "BRIDGE_SPAWN_FAILED", detail: "render-readiness authority unavailable" });
      return;
    }
    const child = childProcess.spawn(python, ["-m", MODULE, "render-readiness"], {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" },
      windowsHide: true,
    });
    let out = "";
    let done = false;
    const finish = (r: ReadinessResponse) => {
      if (done) return;
      done = true;
      resolveOut(r);
    };
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      finish({ ok: false, state: "NOT_READY", error_code: "BRIDGE_TIMEOUT", detail: "render-readiness bridge timed out" });
    }, 60000);
    child.stdout.on("data", (b: Buffer) => {
      out += b.toString("utf8");
      if (out.length > MAX) { try { child.kill("SIGKILL"); } catch {} }
    });
    child.on("error", () => {
      clearTimeout(timer);
      finish({ ok: false, state: "NOT_READY", error_code: "BRIDGE_SPAWN_FAILED", detail: "render-readiness authority unavailable" });
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out.trim() || "{}");
        finish({
          ok: Boolean(parsed.ok),
          state: parsed.state ?? "NOT_READY",
          error_code: parsed.error_code ?? null,
          detail: parsed.detail ?? null,
          checks: parsed.checks ?? undefined,
          projection: parsed.projection ?? undefined,
        });
      } catch {
        finish({ ok: false, state: "NOT_READY", error_code: "BRIDGE_MALFORMED_OUTPUT", detail: "render-readiness authority returned malformed output" });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}
