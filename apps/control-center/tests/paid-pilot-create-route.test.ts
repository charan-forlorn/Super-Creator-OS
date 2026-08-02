import { afterEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const invokeCreateCanonical = vi.fn<(operation: string, payload: Record<string, unknown>) => Promise<Record<string, unknown>>>();
vi.mock("@/lib/paid-pilot-create-bridge", () => ({ invokeCreateCanonical }));

async function post(body: Record<string, unknown>) {
  const { POST } = await import("@/app/api/paid-pilot/create/route");
  const req = new Request("http://local/api/paid-pilot/create", { method: "POST", body: JSON.stringify(body) });
  return POST(req as unknown as NextRequest);
}

afterEach(() => invokeCreateCanonical.mockReset());

const PASS = {
  ok: true,
  error_code: null,
  detail: null,
  canonical_internal_project_id: "spp-3f9a1c2d4e5b",
  pilot_safe_id: "spp-3f9a1c2d4e5b",
  project_safe_id: "spp-3f9a1c2d4e5b",
  external_project_ref: "PILOT-2026-001-PROJ-01",
  admission_packet_sha256: "c4784164…",
  replay: false,
  materialization: { output_profile: "vertical_9_16", dimensions: "1080x1920", duration_seconds: 30, asset_count: 3, mock_references: [] },
  next_safe_action: "Review technical evidence; no render/delivery is authorized.",
};

describe("paid-pilot canonical-create route (§6.E/§6.F bridge)", () => {
  it("creates canonical spp-* project from admitted packet", async () => {
    invokeCreateCanonical.mockResolvedValue(PASS);
    const res = await post({ operation: "create-canonical-project", idempotency_key: "create-x" });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.canonical_internal_project_id).toMatch(/^spp-[a-f0-9]{12}$/);
    expect(body.materialization.dimensions).toBe("1080x1920");
  });

  it("rejects unknown operation", async () => {
    invokeCreateCanonical.mockResolvedValue(PASS);
    const res = await post({ operation: "evil", idempotency_key: "x" });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("UNKNOWN_OPERATION");
  });

  it("strips browser-supplied path fields (security)", async () => {
    invokeCreateCanonical.mockResolvedValue(PASS);
    const res = await post({ operation: "create-canonical-project", idempotency_key: "x", packet_path: "/evil/x.json", hvs_projects_root: "/evil" });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("FORBIDDEN_FIELD");
    // The bridge is never called with forbidden path-shaped fields.
    expect(invokeCreateCanonical).not.toHaveBeenCalled();
  });

  it("rejects malformed idempotency key", async () => {
    invokeCreateCanonical.mockResolvedValue(PASS);
    const res = await post({ operation: "create-canonical-project", idempotency_key: "../../etc/passwd" });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("IDEMPOTENCY_KEY_INVALID");
  });

  it("forwards failure without write", async () => {
    invokeCreateCanonical.mockResolvedValue({ ok: false, error_code: "NO_ADMISSION_RECORD", detail: "none" });
    const res = await post({ operation: "create-canonical-project", idempotency_key: "x" });
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });

  it("no absolute path / secret leakage in response", async () => {
    invokeCreateCanonical.mockResolvedValue(PASS);
    const res = await post({ operation: "create-canonical-project", idempotency_key: "x" });
    const body = await res.json();
    expect(JSON.stringify(body)).not.toMatch(/C:\\|secret|NODE_ENV/);
  });
});
