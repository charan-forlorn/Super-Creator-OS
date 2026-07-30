import { describe, expect, it, beforeAll, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";

// Cohort 10K — route/bridge smoke for the Brief Studio brief-section op.
import { invokeIntake } from "@/lib/paid-pilot-intake-bridge";
import { POST } from "@/app/api/paid-pilot/intake/route";

// Reuse the reviewed same-origin route with the new brief-section allow-list entry.

function makeReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/paid-pilot/intake", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeAll(() => {
  process.env.SCOS_REPO_ROOT = "C:/Workspace/scos-cohort10k-brief-studio-20260730T210456Z";
  process.env.SCOS_PYTHON_INTERPRETER = "C:/Workspace/super-creator-os/.venv/Scripts/python.exe";
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("POST /api/paid-pilot/intake — brief-section", () => {
  it("rejects an unknown operation with 400 and no stack trace", async () => {
    const res = await POST(makeReq({ operation: "hack", draft_id: "x" }));
    expect(res.status).toBe(400);
    const j = await res.json();
    expect(j.ok).toBe(false);
    expect(j.error_code).toBe("UNKNOWN_OPERATION");
    expect(JSON.stringify(j)).not.toMatch(/Traceback|stack|C:\\\\/);
  });

  it("runs a real child process for a valid brief-section write and returns the authoritative projection", async () => {
    const store = "C:/Users/chara/AppData/Local/Temp/coh10k-brief-route-store.json";
    const create = await POST(makeReq({ operation: "draft", store_path: store, safe_project_title: "Synthetic Brief", deadline: "2026-08-15", rights_answers: { asset_owner: "Owned", identifiable_person: "No", voice_used: "Not used", music_used: "Not used", font_policy: "Licensed" }, privacy_answers: { health_data: "No", financial_data: "No", government_identifiers: "No", child_information: "No" } }));
    expect(create.status).toBe(200);
    const cj = await create.json();
    const did = cj.draft.draft_id;
    expect(did).toBeTruthy();

    const res = await POST(makeReq({ operation: "brief-section", draft_id: did, section_id: "goal", answers: { goal: "วิดีโอให้ความรู้" }, store_path: store }));
    expect(res.status).toBe(200);
    const j = await res.json();
    expect(j.ok).toBe(true);
    expect(j.draft.brief_answers.goal).toBe("วิดีโอให้ความรู้");
    expect(j.draft.generated.brief.readiness_label).toMatch(/พร้อมแล้ว \d+ จาก 8 ส่วน/);
  });

  it("maps a missing interpreter to a safe bridge error (no path/credential leak)", async () => {
    const saved = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = "/nonexistent/python.exe";
    const res = await POST(makeReq({ operation: "brief-section", draft_id: "x", section_id: "goal", answers: {} }));
    expect([400, 409]).toContain(res.status);
    const j = await res.json();
    expect(j.ok).toBe(false);
    expect(j.error_code).toMatch(/BRIDGE_/);
    expect(JSON.stringify(j)).not.toMatch(/Traceback|password|token/i);
    process.env.SCOS_PYTHON_INTERPRETER = saved;
  });

  it("bounds oversized payloads", async () => {
    const res = await POST(makeReq({ operation: "brief-section", draft_id: "x", section_id: "goal", answers: { goal: "x".repeat(40000) } }));
    expect(res.status).toBe(413);
    const j = await res.json();
    expect(j.error_code).toBe("REQUEST_TOO_LARGE");
  });
});
