
import * as childProcess from "node:child_process";
import * as fs from "node:fs";
import { dirname, join, resolve } from "node:path";
import type { IntakeResponse } from "./paid-pilot-intake-types";

const MODULE = "scos.control_center.hvs_guided_pilot_intake_cli";
const MAX = 1_048_576;

// The repo root is derived from the server process cwd, never from any
// browser-supplied value. It is used as both the spawn cwd and PYTHONPATH so
// the committed SCOS source resolves from the detached worktree.
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

// Deterministic, server-controlled interpreter resolution.
// The browser cannot influence the executable, cwd, or module.
//
// If SCOS_PYTHON_INTERPRETER is set it is the server's authoritative choice:
// it is used only when it exists, otherwise we fail closed (no silent fallback
// to a different interpreter). When it is unset we discover a repo-relative
// venv (worktree .venv, then sibling super-creator-os/.venv). If none exists
// we fail closed. No shell-PATH guessing is ever used.
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

export function invokeIntake(operation: string, payload: Record<string, unknown>): Promise<IntakeResponse> {
  return new Promise((resolveOut) => {
    const root = repoRoot();
    const python = resolvePython();
    if (!python) {
      resolveOut({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "guided intake authority unavailable", draft: null });
      return;
    }
    const child = childProcess.spawn(python, ["-m", MODULE, operation], {
      cwd: root,
      env: { ...process.env, PYTHONPATH: root, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" },
      windowsHide: true,
    });
    let out = "";
    let done = false;
    const finish = (r: IntakeResponse) => { if (done) return; done = true; resolveOut(r); };
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      finish({ ok: false, error_code: "BRIDGE_TIMEOUT", detail: "guided intake bridge timed out", draft: null });
    }, 60000);
    child.stdout.on("data", (b: Buffer) => {
      out += b.toString("utf8");
      if (out.length > MAX) { try { child.kill("SIGKILL"); } catch {} }
    });
    child.on("error", () => {
      clearTimeout(timer);
      finish({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "guided intake authority unavailable", draft: null });
    });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out.trim() || "{}");
        finish({
          ok: Boolean(parsed.ok),
          error_code: parsed.error_code ?? null,
          detail: parsed.detail ?? null,
          draft: parsed.draft ?? null,
          replay: parsed.replay,
          pilot_safe_id: parsed.pilot_safe_id,
          project_safe_id: parsed.project_safe_id,
          admission_packet_sha256: parsed.admission_packet_sha256,
          next_safe_action: parsed.next_safe_action,
        });
      } catch {
        finish({ ok: false, error_code: "BRIDGE_MALFORMED_OUTPUT", detail: "guided intake authority returned malformed output", draft: null });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}
