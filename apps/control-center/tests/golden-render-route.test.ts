import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { POST as executePost } from "@/app/api/golden-render/execute/route";

const PROJECT = "coh10g_v";

// A deterministic stub interpreter that emulates the Python golden-render
// bridge WITHOUT performing a real (slow) HVS render. It echoes the exact
// structured response the real bridge returns on success, so the route
// contract (validation, shaping, no-secret masking) is covered in CI without
// a 2-minute render. The real render path is exercised separately by the
// Cohort 10G driver (scripts/coh10g_real_render_driver.py).
let stubModuleDir: string;
let storePath: string;
let prevInterp: string | undefined;
let prevStore: string | undefined;
let prevHvs: string | undefined;
let prevPath: string | undefined;
let prevModule: string | undefined;

function writeStub() {
  stubModuleDir = mkdtempSync(resolve(tmpdir(), "golden-stub-mod-"));
  // A uniquely-named stub module (only present in the stub dir) so it is
  // imported ahead of the real bridge regardless of cwd sys.path[0].
  const body = [
    "import sys, json",
    "def main():",
    "    raw = sys.stdin.read() if not sys.stdin.isatty() else '{}'",
    "    try:",
    "        args = json.loads(raw) if raw.strip() else {}",
    "    except Exception:",
    "        args = {}",
    "    op = sys.argv[1] if len(sys.argv) > 1 else 'execute'",
    "    prof = args.get('profile_id', 'vertical_9_16')",
    "    if op == 'execute':",
    "        out = {",
    "          'ok': True,",
    "          'state': 'RENDER_SUCCEEDED',",
    "          'attempt_id': 'stub-attempt-1',",
    "          'artifact_id': 'stub-artifact-1',",
    "          'artifact_checksum': 'a' * 64,",
    "          'render_calls': 1,",
    "          'hvs_calls': 2,",
    "          'qa_overall_state': 'QA_PASSED',",
    "          'qa_report_id': 'qa-stub-1',",
    "          'qa_failure_codes': [],",
    "          'attempt': {'render_state': 'RENDER_SUCCEEDED', 'profile_id': prof},",
    "          'qa_report': {'overall_state': 'QA_PASSED', 'checks': []},",
    "        }",
    "    else:",
    "        out = {'ok': True, 'attempts': [], 'supported_profiles': ['vertical_9_16','square_1_1','landscape_16_9']}",
    "    sys.stdout.write(json.dumps(out))",
    "    sys.exit(0)",
    "if __name__ == '__main__':",
    "    main()",
  ].join("\n");
  writeFileSync(`${stubModuleDir}/golden_render_stub.py`, body);
}

function post(url: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${url}`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  writeStub();
  storePath = mkdtempSync(resolve(tmpdir(), "golden-route-store-"));
  prevInterp = process.env.SCOS_PYTHON_INTERPRETER;
  prevStore = process.env.SCOS_GOLDEN_RENDER_STORE_PATH;
  prevHvs = process.env.SCOS_HVS_REPO_PATH;
  process.env.SCOS_PYTHON_INTERPRETER = prevInterp && prevInterp.length ? prevInterp : "C:/Users/chara/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe";
  process.env.SCOS_GOLDEN_RENDER_STORE_PATH = storePath;
  // Point the bridge at the deterministic stub module (only in stubDir).
  prevPath = process.env.SCOS_BRIDGE_EXTRA_PATH;
  prevModule = process.env.SCOS_BRIDGE_MODULE;
  process.env.SCOS_BRIDGE_EXTRA_PATH = stubModuleDir;
  process.env.SCOS_BRIDGE_MODULE = "golden_render_stub";
});

afterEach(() => {
  if (prevInterp === undefined) delete process.env.SCOS_PYTHON_INTERPRETER;
  else process.env.SCOS_PYTHON_INTERPRETER = prevInterp;
  if (prevStore === undefined) delete process.env.SCOS_GOLDEN_RENDER_STORE_PATH;
  else process.env.SCOS_GOLDEN_RENDER_STORE_PATH = prevStore;
  if (prevHvs === undefined) delete process.env.SCOS_HVS_REPO_PATH;
  else process.env.SCOS_HVS_REPO_PATH = prevHvs;
  if (prevPath === undefined) delete process.env.SCOS_BRIDGE_EXTRA_PATH;
  else process.env.SCOS_BRIDGE_EXTRA_PATH = prevPath;
  if (prevModule === undefined) delete process.env.SCOS_BRIDGE_MODULE;
  else process.env.SCOS_BRIDGE_MODULE = prevModule;
  try { rmSync(storePath, { recursive: true, force: true }); } catch { /* ignore */ }
  try { rmSync(stubModuleDir, { recursive: true, force: true }); } catch { /* ignore */ }
});

describe("Cohort 10G golden-render route — contract + fail-closed", () => {
  it("rejects malformed project ids with no stack trace", async () => {
    const res = await executePost(post("/api/golden-render/execute", {
      projectId: "../evil", hvsProjectId: "46a92c8eab20", profileId: "vertical_9_16",
      authorizationId: "az_v_001", operatorId: "op",
    }));
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.error_code).toBe("PROJECT_NOT_FOUND");
    expect(JSON.stringify(body)).not.toMatch(/at\s+\w|Error:|stack/i);
  });

  it("rejects unexpected fields (no arbitrary path input)", async () => {
    const res = await executePost(post("/api/golden-render/execute", {
      projectId: PROJECT, hvsProjectId: "46a92c8eab20", profileId: "vertical_9_16",
      authorizationId: "az_v_001", operatorId: "op", evilPath: "C:/Workspace/hermes-video-studio",
    }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("REQUEST_UNEXPECTED_FIELD");
  });

  it("rejects an unsupported profile id", async () => {
    const res = await executePost(post("/api/golden-render/execute", {
      projectId: PROJECT, hvsProjectId: "46a92c8eab20", profileId: "vertical",
      authorizationId: "az_v_001", operatorId: "op",
    }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("REQUEST_MALFORMED");
  });

  it("invokes the bridge exactly once and shapes a successful result", async () => {
    const res = await executePost(post("/api/golden-render/execute", {
      projectId: PROJECT, hvsProjectId: "46a92c8eab20", profileId: "vertical_9_16",
      authorizationId: "az_v_001", operatorId: "op",
    }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.result.state).toBe("RENDER_SUCCEEDED");
    expect(body.result.qa_overall_state).toBe("QA_PASSED");
    expect(body.result.render_calls).toBe(1);
    expect(body.result.hvs_calls).toBe(2);
  });

  it("masks a bridge failure with no absolute-path / secret leak", async () => {
    const prevPy = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = "C:/nonexistent/python.exe";
    try {
      const res = await executePost(post("/api/golden-render/execute", {
        projectId: PROJECT, hvsProjectId: "46a92c8eab20", profileId: "vertical_9_16",
        authorizationId: "az_v_001", operatorId: "op",
      }));
      expect(res.status).toBe(409);
      const body = await res.json();
      expect(body.ok).toBe(false);
      expect(JSON.stringify(body)).not.toMatch(/[A-Z]:\\|integrity|\.json\.lock|calibri|secret|token/i);
    } finally {
      process.env.SCOS_PYTHON_INTERPRETER = prevPy;
    }
  });
});
