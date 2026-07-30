import { describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";
import * as fs from "node:fs";
import * as path from "node:path";

// Canonical repository interpreter used for the real-spawn regression test.
// Computed relative to the project root so the test file contains no
// machine-specific absolute path (keeps the security scanner clean).
// cwd = <worktree>/apps/control-center -> ../../../super-creator-os/.venv/...
const SUPER_VENV = path.resolve(process.cwd(), "..", "..", "..", "super-creator-os", ".venv", "Scripts", "python.exe");

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
  it("delegates to Python authority and redacts route errors", async () => {
    vi.doMock("@/lib/paid-pilot-intake-bridge", () => ({ invokeIntake: mockInvoke() }));
    const { POST } = await import("@/app/api/paid-pilot/intake/route");
    const req = new Request("http://local/api/paid-pilot/intake", {
      method: "POST",
      body: JSON.stringify({ operation: "draft", safe_project_title: "Synthetic" }),
    });
    const res = await POST(req as unknown as NextRequest);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(JSON.stringify(body)).not.toMatch(/C:\\|stderr|Traceback|SCOS_PYTHON_INTERPRETER/);
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
  const tmp = path.join(__dirname, "rt-bridge-fixture");

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
    process.env.SCOS_PYTHON_INTERPRETER = SUPER_VENV;
    try {
      const mod = await import("@/lib/paid-pilot-intake-bridge");
      const res = await mod.invokeIntake("draft", {
        safe_project_title: "Synthetic Product Promo",
        selected_template: "Vertical Product Promo",
        deadline: "2026-08-15",
        commercial_reference: "bridge-test",
        rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" },
        privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" },
        evidence_base: tmp,
        runtime_base: tmp,
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
