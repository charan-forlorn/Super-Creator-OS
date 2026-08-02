import { describe, expect, it, vi, beforeAll, afterAll } from "vitest";
import type { NextRequest } from "next/server";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

function resolveInterpreterForTest(): string {
  const explicit = process.env.SCOS_PYTHON_INTERPRETER;
  if (explicit && fs.existsSync(explicit)) return explicit;
  let candidate = process.cwd();
  for (let i = 0; i < 5; i++) {
    for (const rel of [["Scripts", "python.exe"], ["bin", "python"]]) {
      const p = path.resolve(candidate, ".venv", ...(rel as [string, string]));
      if (fs.existsSync(p)) return p;
    }
    candidate = path.dirname(candidate);
  }
  // Last resort: a python3 shim on PATH (materialised by the canonical verifier).
  for (const entry of (process.env.PATH ?? "").split(path.delimiter)) {
    if (!entry) continue;
    const p = path.join(entry, process.platform === "win32" ? "python3.exe" : "python3");
    if (fs.existsSync(p)) return p;
  }
  return "";
}

function mockInvoke() {
  return vi.fn(async (op: string, payload: Record<string, unknown>) => {
    if (payload.idempotency_key === "conflict-draft-1") {
      return {
        ok: false,
        error_code: "CONFLICTING_REPLAY_REJECTED",
        detail: "idempotency key conflicts with existing creation",
        draft: null,
      };
    }
    return {
      ok: true,
      error_code: null,
      detail: null,
      replay: op === "create" && payload.idempotency_key === "create-draft-1",
      pilot_safe_id: op === "create" ? "pilot-1" : undefined,
      project_safe_id: op === "create" ? "project-1" : undefined,
      admission_packet_sha256: op === "create" ? "b".repeat(64) : undefined,
      draft: {
        draft_id: payload.draft_id ?? "draft-1",
        status: op === "create" ? "CREATED" : "READY_TO_CREATE",
        safe_project_title: "Synthetic",
        selected_template: "Vertical Product Promo",
        target_platform: "TikTok",
        output_profile: "vertical_9_16",
        duration: "30s",
        deadline: "2026-08-15",
        commercial_reference: "synthetic",
        asset_references: [],
        consent_state: "CONSENT_CONFIRMED",
        consent_evidence_reference: "redacted.txt",
        consent_evidence_sha256: "a".repeat(64),
        explicit_consent_confirmed: true,
        rights_answers: {},
        privacy_answers: {},
        derived_classification: "STANDARD_COMMERCIAL",
        retention_policy: "30 days",
        external_action_restrictions: { upload: "NOT_AUTHORIZED" },
        validation_findings: [],
        generated: {},
        created_at: "t",
        updated_at: "t",
        revision: 1,
        pilot_safe_id: "pilot-1",
        project_safe_id: "project-1",
        admission_packet_sha256: "b".repeat(64),
      },
    };
  });
}

describe("paid-pilot guided intake route", () => {
  it("delegates to Python authority and redacts route errors, sends no filesystem path", async () => {
    vi.doMock("@/lib/paid-pilot-intake-bridge", () => ({ invokeIntake: mockInvoke() }));
    const { POST } = await import("@/app/api/paid-pilot/intake/route");
    const raw = JSON.stringify({ operation: "draft", safe_project_title: "Synthetic", store_path: "C:/Workspace/scos-paid-pilot-evidence/x.json", runtime_base: "C:/Workspace/scos-paid-pilot/y", evidence_base: "C:/Workspace/scos-paid-pilot/z" });
    const req = new Request("http://local/api/paid-pilot/intake", {
      method: "POST",
      body: raw,
    });
    const res = await POST(req as unknown as NextRequest);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    // The stripped path fields must never reach the response or be echoed.
    expect(raw).toContain("store_path");
    expect(JSON.stringify(body)).not.toMatch(/C:\\\\|C:\/|scos-paid-pilot|store_path|runtime_base|evidence_base|SCOS_PILOT_/);
    expect(JSON.stringify(body)).not.toMatch(/stderr|Traceback|SCOS_PYTHON_INTERPRETER/);
  });

  it("rejects unknown operations", async () => {
    vi.doMock("@/lib/paid-pilot-intake-bridge", () => ({
      invokeIntake: vi.fn(async () => ({ ok: true, draft: { status: "READY_TO_CREATE", draft_id: "draft-1" } })),
    }));
    const { POST } = await import("@/app/api/paid-pilot/intake/route");
    const req = new Request("http://local/api/paid-pilot/intake", {
      method: "POST",
      body: JSON.stringify({ operation: "send-customer-message" }),
    });
    const res = await POST(req as unknown as NextRequest);
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("UNKNOWN_OPERATION");
  });

  it("exact replay remains idempotent and conflicting replay remains rejected", async () => {
    vi.doMock("@/lib/paid-pilot-intake-bridge", () => ({
      invokeIntake: vi.fn(async (op: string, payload: Record<string, unknown>) => {
        if (payload.idempotency_key === "conflict-draft-1") {
          return { ok: false, error_code: "CONFLICTING_REPLAY_REJECTED", detail: "x", draft: null };
        }
        return {
          ok: true,
          replay: op === "create" && payload.idempotency_key === "create-draft-1",
          pilot_safe_id: "pilot-1",
          project_safe_id: "project-1",
          draft: { draft_id: "draft-1", status: op === "create" ? "CREATED" : "READY_TO_CREATE" },
        };
      }),
    }));
    const { POST } = await import("@/app/api/paid-pilot/intake/route");

    const exact = new Request("http://local/api/paid-pilot/intake", {
      method: "POST",
      body: JSON.stringify({ operation: "create", draft_id: "draft-1", idempotency_key: "create-draft-1" }),
    });
    const exactRes = await POST(exact as unknown as NextRequest);
    expect(exactRes.status).toBe(200);
    const exactBody = await exactRes.json();
    expect(exactBody.replay).toBe(true);
    expect(exactBody.pilot_safe_id).toBe("pilot-1");
    expect(exactBody.project_safe_id).toBe("project-1");

    const conflict = new Request("http://local/api/paid-pilot/intake", {
      method: "POST",
      body: JSON.stringify({ operation: "create", draft_id: "draft-1", idempotency_key: "conflict-draft-1" }),
    });
    const conflictRes = await POST(conflict as unknown as NextRequest);
    expect(conflictRes.status).toBe(409);
    const conflictBody = await conflictRes.json();
    expect(conflictBody.error_code).toBe("CONFLICTING_REPLAY_REJECTED");
  });
});

describe("guided intake bridge real spawn", () => {
  // R2.1: task-owned roots come from the server process environment only.
  // A fresh OS-temp directory owns all state — never a repo-local path and
  // never the operator/CI shared root.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "scos-pp-route-"));

  const MANAGED_KEYS = [
    "SCOS_PYTHON_INTERPRETER",
    "SCOS_PILOT_INTAKE_STORE", "SCOS_PILOT_PACKET_ADMISSION_STORE", "SCOS_PILOT_AUDIT_STORE",
    "SCOS_PILOT_AUTHORIZATION_STORE", "SCOS_PILOT_MATERIALIZATION_STATE", "SCOS_PILOT_HVS_PROJECTS_ROOT",
    "SCOS_PILOT_RENDER_READINESS_STATE", "SCOS_PILOT_OUTPUT_ROOT", "SCOS_PILOT_APPROVED_INPUT_ROOT",
    "SCOS_PILOT_INTAKE_RUNTIME_BASE", "SCOS_PILOT_INTAKE_EVIDENCE_BASE",
  ] as const;

  function setRoots() {
    for (const key of MANAGED_KEYS) ORIGINAL_ENV[key] = process.env[key];
    process.env.SCOS_PILOT_INTAKE_STORE = path.join(tmp, "intake-store.json");
    process.env.SCOS_PILOT_PACKET_ADMISSION_STORE = path.join(tmp, "adm.json");
    process.env.SCOS_PILOT_AUDIT_STORE = path.join(tmp, "audit.jsonl");
    process.env.SCOS_PILOT_AUTHORIZATION_STORE = path.join(tmp, "auth.json");
    process.env.SCOS_PILOT_MATERIALIZATION_STATE = path.join(tmp, "mat.json");
    process.env.SCOS_PILOT_HVS_PROJECTS_ROOT = path.join(tmp, "hvs-projects");
    process.env.SCOS_PILOT_RENDER_READINESS_STATE = path.join(tmp, "rr.json");
    process.env.SCOS_PILOT_OUTPUT_ROOT = path.join(tmp, "output");
    process.env.SCOS_PILOT_APPROVED_INPUT_ROOT = path.join(tmp, "approved-input");
    process.env.SCOS_PILOT_INTAKE_RUNTIME_BASE = path.join(tmp, "runtime");
    process.env.SCOS_PILOT_INTAKE_EVIDENCE_BASE = path.join(tmp, "evidence");
  }

  const ORIGINAL_ENV: Record<string, string | undefined> = {};

  function restoreRoots() {
    for (const key of MANAGED_KEYS) {
      const original = ORIGINAL_ENV[key];
      if (original === undefined) delete process.env[key];
      else process.env[key] = original;
    }
  }

  beforeAll(() => {
    setRoots();
  });

  afterAll(() => {
    restoreRoots();
    fs.rmSync(tmp, { recursive: true, force: true });
  });

  it("fails closed when the configured interpreter is missing", async () => {
    vi.doUnmock("@/lib/paid-pilot-intake-bridge");
    vi.resetModules();
    const prev = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = path.join(tmp, "does-not-exist.exe");
    try {
      const mod = await import("@/lib/paid-pilot-intake-bridge");
      const res = await mod.invokeIntake("draft", {});
      expect(res.ok).toBe(false);
      expect(res.error_code).toBe("BRIDGE_SPAWN_FAILED");
    } finally {
      if (prev === undefined) delete process.env.SCOS_PYTHON_INTERPRETER;
      else process.env.SCOS_PYTHON_INTERPRETER = prev;
    }
  });

  it("starts the committed CLI with a server-controlled interpreter", async () => {
    vi.doUnmock("@/lib/paid-pilot-intake-bridge");
    vi.resetModules();
    const prev = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = resolveInterpreterForTest();
    try {
      const mod = await import("@/lib/paid-pilot-intake-bridge");
      const res = await mod.invokeIntake("draft", {
        safe_project_title: "Synthetic Product Promo",
        selected_template: "Vertical Product Promo",
        deadline: "2026-08-15",
        commercial_reference: "bridge-test",
        rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" },
        privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" },
      });
      expect(res.ok).toBe(true);
      expect(res.draft?.draft_id).toBeTruthy();
      expect(res.draft?.status).toBeTruthy();
    } finally {
      if (prev === undefined) delete process.env.SCOS_PYTHON_INTERPRETER;
      else process.env.SCOS_PYTHON_INTERPRETER = prev;
    }
  });
});
