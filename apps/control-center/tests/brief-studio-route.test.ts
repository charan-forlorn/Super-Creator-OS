import { describe, expect, it, beforeAll, afterAll, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { delimiter, dirname, join, resolve } from "node:path";
import { tmpdir } from "node:os";

// Cohort 10K — route/bridge smoke for the Brief Studio brief-section op.
import { POST } from "@/app/api/paid-pilot/intake/route";

// Reuse the reviewed same-origin route with the new brief-section allow-list entry.

// ---------------------------------------------------------------------------
// Repository root resolution.
//
// The test must run against the CURRENT worktree — never a hardcoded cohort
// path and never the live repository. This mirrors the repository-owned
// mechanism already implemented by repoRoot() in lib/paid-pilot-intake-bridge.ts:
// walk up from the process cwd until the committed SCOS source is found.
// Vitest runs with cwd = <worktree>/apps/control-center, so the walk resolves
// the enclosing worktree deterministically on any machine and in CI.
// ---------------------------------------------------------------------------
function resolveRepoRoot(): string {
  let candidate = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (existsSync(join(candidate, "scos", "control_center"))) return candidate;
    candidate = dirname(candidate);
  }
  throw new Error("committed SCOS source not found above the test working directory");
}

// ---------------------------------------------------------------------------
// Interpreter resolution — deterministic and server-controlled, in the same
// order the repository already uses:
//   1. an existing SCOS_PYTHON_INTERPRETER supplied by the canonical verifier
//   2. a worktree-local .venv
//   3. the sibling super-creator-os .venv (repo-relative, no machine literal)
//   4. an explicit PATH scan for python3/python (no shell, no guessing)
// No absolute machine-specific path is embedded in this file.
// ---------------------------------------------------------------------------
function resolveInterpreter(root: string): string | null {
  const explicit = process.env.SCOS_PYTHON_INTERPRETER;
  if (explicit && existsSync(explicit)) return explicit;

  const candidates = [
    resolve(root, ".venv", "Scripts", "python.exe"),
    resolve(root, ".venv", "bin", "python"),
    resolve(root, "..", "super-creator-os", ".venv", "Scripts", "python.exe"),
    resolve(root, "..", "super-creator-os", ".venv", "bin", "python"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }

  for (const entry of (process.env.PATH ?? "").split(delimiter)) {
    if (!entry) continue;
    for (const name of ["python3.exe", "python3", "python.exe", "python"]) {
      const candidate = join(entry, name);
      if (existsSync(candidate)) return candidate;
    }
  }
  return null;
}

const REPO_ROOT = resolveRepoRoot();

// Runtime/store root: a fresh OS-temp directory owned by this test invocation.
// It is unique per run and lives outside every Git worktree, so no
// repository-local runtime residue (e.g. tests/rt-bridge-fixture/) is created.
let RUNTIME_ROOT = "";
let STORE_PATH = "";

const ORIGINAL_ENV: Record<string, string | undefined> = {};
const MANAGED_KEYS = [
  "SCOS_REPO_ROOT", "SCOS_PYTHON_INTERPRETER", "PYTHONPATH",
  // R2.1 task-owned roots (server-controlled; never from request body).
  "SCOS_PILOT_INTAKE_STORE", "SCOS_PILOT_PACKET_ADMISSION_STORE", "SCOS_PILOT_AUDIT_STORE",
  "SCOS_PILOT_AUTHORIZATION_STORE", "SCOS_PILOT_MATERIALIZATION_STATE", "SCOS_PILOT_HVS_PROJECTS_ROOT",
  "SCOS_PILOT_RENDER_READINESS_STATE", "SCOS_PILOT_OUTPUT_ROOT", "SCOS_PILOT_APPROVED_INPUT_ROOT",
  "SCOS_PILOT_INTAKE_RUNTIME_BASE", "SCOS_PILOT_INTAKE_EVIDENCE_BASE",
] as const;

function makeReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/paid-pilot/intake", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeAll(() => {
  for (const key of MANAGED_KEYS) ORIGINAL_ENV[key] = process.env[key];

  RUNTIME_ROOT = mkdtempSync(join(tmpdir(), "scos-brief-route-"));
  STORE_PATH = join(RUNTIME_ROOT, "guided-intake-store.json");

  const interpreter = resolveInterpreter(REPO_ROOT);
  if (!interpreter) throw new Error("no deterministic Python interpreter available for the bridge test");

  // Process-local only. The child cwd and PYTHONPATH are the current worktree,
  // so the committed CLI under test is the one that executes.
  process.env.SCOS_REPO_ROOT = REPO_ROOT;
  process.env.SCOS_PYTHON_INTERPRETER = interpreter;
  process.env.PYTHONPATH = REPO_ROOT;
  // R2.1: task-owned roots are resolved server-side from environment. The route
  // strips any path field from the request body; the CLI resolves these roots.
  process.env.SCOS_PILOT_INTAKE_STORE = STORE_PATH;
  process.env.SCOS_PILOT_PACKET_ADMISSION_STORE = join(RUNTIME_ROOT, "adm.json");
  process.env.SCOS_PILOT_AUDIT_STORE = join(RUNTIME_ROOT, "audit.jsonl");
  process.env.SCOS_PILOT_AUTHORIZATION_STORE = join(RUNTIME_ROOT, "auth.json");
  process.env.SCOS_PILOT_MATERIALIZATION_STATE = join(RUNTIME_ROOT, "mat.json");
  process.env.SCOS_PILOT_HVS_PROJECTS_ROOT = join(RUNTIME_ROOT, "hvs-projects");
  process.env.SCOS_PILOT_RENDER_READINESS_STATE = join(RUNTIME_ROOT, "rr.json");
  process.env.SCOS_PILOT_OUTPUT_ROOT = join(RUNTIME_ROOT, "output");
  process.env.SCOS_PILOT_APPROVED_INPUT_ROOT = join(RUNTIME_ROOT, "approved-input");
  process.env.SCOS_PILOT_INTAKE_RUNTIME_BASE = join(RUNTIME_ROOT, "runtime");
  process.env.SCOS_PILOT_INTAKE_EVIDENCE_BASE = join(RUNTIME_ROOT, "evidence");
});

afterAll(() => {
  for (const key of MANAGED_KEYS) {
    const original = ORIGINAL_ENV[key];
    if (original === undefined) delete process.env[key];
    else process.env[key] = original;
  }
  if (RUNTIME_ROOT) rmSync(RUNTIME_ROOT, { recursive: true, force: true });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("POST /api/paid-pilot/intake — brief-section", () => {
  it("resolves the current worktree as the child runtime root, never a live or removed worktree", () => {
    expect(existsSync(REPO_ROOT)).toBe(true);
    expect(existsSync(join(REPO_ROOT, "scos", "control_center"))).toBe(true);
    expect(process.env.SCOS_REPO_ROOT).toBe(REPO_ROOT);
    // The runtime/store root this test owns is a unique OS-temp directory,
    // outside the repository worktree, so this file leaves no repository-local
    // runtime residue. (Residue owned by other test files is out of scope here.)
    expect(RUNTIME_ROOT.startsWith(REPO_ROOT)).toBe(false);
    expect(RUNTIME_ROOT.startsWith(tmpdir())).toBe(true);
    expect(STORE_PATH.startsWith(RUNTIME_ROOT)).toBe(true);
  });

  it("rejects an unknown operation with 400 and no stack trace", async () => {
    const res = await POST(makeReq({ operation: "hack", draft_id: "x" }));
    expect(res.status).toBe(400);
    const j = await res.json();
    expect(j.ok).toBe(false);
    expect(j.error_code).toBe("UNKNOWN_OPERATION");
    expect(JSON.stringify(j)).not.toMatch(/Traceback|stack|C:\\\\/);
  });

  it("runs a real child process for a valid brief-section write and returns the authoritative projection", async () => {
    const create = await POST(makeReq({ operation: "draft", safe_project_title: "Synthetic Brief", deadline: "2026-08-15", rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" }, privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" } }));
    expect(create.status).toBe(200);
    const cj = await create.json();
    const did = cj.draft.draft_id;
    expect(did).toBeTruthy();
    // The store was written by the real child process, outside the repository.
    expect(existsSync(STORE_PATH)).toBe(true);

    const res = await POST(makeReq({ operation: "brief-section", draft_id: did, section_id: "goal", answers: { goal: "วิดีโอให้ความรู้" } }));
    expect(res.status).toBe(200);
    const j = await res.json();
    expect(j.ok).toBe(true);
    expect(j.draft.brief_answers.goal).toBe("วิดีโอให้ความรู้");
    expect(j.draft.generated.brief.readiness_label).toMatch(/พร้อมแล้ว \d+ จาก 8 ส่วน/);
  });

  it("maps a missing interpreter to a safe bridge error (no path/credential leak)", async () => {
    const saved = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = join(RUNTIME_ROOT, "does-not-exist-python.exe");
    try {
      const res = await POST(makeReq({ operation: "brief-section", draft_id: "x", section_id: "goal", answers: {} }));
      // A genuine bridge failure must stay a 409 — never a false 200 success.
      expect(res.status).toBe(409);
      const j = await res.json();
      expect(j.ok).toBe(false);
      expect(j.error_code).toMatch(/BRIDGE_/);
      expect(JSON.stringify(j)).not.toMatch(/Traceback|password|token/i);
    } finally {
      if (saved === undefined) delete process.env.SCOS_PYTHON_INTERPRETER;
      else process.env.SCOS_PYTHON_INTERPRETER = saved;
    }
  });

  it("keeps a genuine authority rejection at 409 without leaking internals", async () => {
    const res = await POST(makeReq({ operation: "brief-section", draft_id: "missing-draft-id", section_id: "goal", answers: { goal: "x" } }));
    expect(res.status).toBe(409);
    const j = await res.json();
    expect(j.ok).toBe(false);
    expect(j.error_code).toBe("DRAFT_NOT_FOUND");
    expect(JSON.stringify(j)).not.toMatch(/Traceback|SCOS_PYTHON_INTERPRETER/);
  });

  it("bounds oversized payloads", async () => {
    const res = await POST(makeReq({ operation: "brief-section", draft_id: "x", section_id: "goal", answers: { goal: "x".repeat(40000) } }));
    expect(res.status).toBe(413);
    const j = await res.json();
    expect(j.error_code).toBe("REQUEST_TOO_LARGE");
  });

  it("sends no filesystem path field in the request body", async () => {
    const body = {
      operation: "draft",
      safe_project_title: "Synthetic Brief",
      rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" },
      privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" },
    };
    const forbidden = ["store_path", "runtime_base", "evidence_base", "approved_input_root", "admission_store", "identity_store", "materialization_store", "readiness_store", "projects_root", "output_root", "contracts_root", "file_path", "directory_path"];
    for (const key of forbidden) expect((body as Record<string, unknown>)[key]).toBeUndefined();
    const req = makeReq(body);
    const raw = await req.text();
    for (const key of forbidden) expect(raw).not.toContain(key);
  });

  it("ignores client-supplied filesystem path fields and returns a path-free response", async () => {
    // A client attempting to inject a shared-operator store path via the
    // request body must have it stripped; roots resolve server-side only.
    const res = await POST(makeReq({
      operation: "draft",
      store_path: "C:/Workspace/scos-paid-pilot-evidence/_guided-intake-store-v1.json",
      safe_project_title: "Synthetic Brief",
      rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" },
      privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" },
    }));
    expect(res.status).toBe(200);
    const j = await res.json();
    const serialized = JSON.stringify(j);
    expect(serialized).not.toMatch(/C:\\\\|C:\/|scos-paid-pilot|SCOS_PILOT_/);
    expect(serialized).not.toMatch(/Traceback|stderr|stack/i);
    // The injected shared-operator path string must not be echoed back.
    expect(serialized).not.toContain("scos-paid-pilot-evidence");
    expect(j.draft.draft_id).toBeTruthy();
  });
});
