import { afterEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const EXPECTED_SHA = "c4784164704988cd7ab6b20bd315c0e67d80b06aadf714a3a3427f4a92dc8c02";

const invokeAdmission = vi.fn<(operation: string, payload: Record<string, unknown>) => Promise<Record<string, unknown>>>();
vi.mock("@/lib/paid-pilot-admission-bridge", () => ({ invokeAdmission }));

async function post(body: Record<string, unknown>) {
  const { POST } = await import("@/app/api/paid-pilot/admission/route");
  const req = new Request("http://local/api/paid-pilot/admission", { method: "POST", body: JSON.stringify(body) });
  return POST(req as unknown as NextRequest);
}

afterEach(() => invokeAdmission.mockReset());

const PASS = {
  ok: true, error_code: null, detail: null,
  gates: [{ token: "PACKET_VALID", passed: true, reason_code: "OK", detail: "ok" }],
  assets: [
    { asset_id: "asset-01", safe_name: "product-front.jpg", status: "OK", purpose: "p", rights_declaration: "Owned", privacy_classification: "STANDARD_COMMERCIAL" },
    { asset_id: "asset-02", safe_name: "customer-logo.png", status: "OK", purpose: "l", rights_declaration: "Owned", privacy_classification: "STANDARD_COMMERCIAL" },
    { asset_id: "asset-03", safe_name: "promo-music-31s.mp3", status: "OK", purpose: "m", rights_declaration: "Owned", privacy_classification: "STANDARD_COMMERCIAL" },
  ],
  projection: {
    schema_version: "scos-hvs.pilot-packet-admission.v1/1.0.0",
    packet_sha256: EXPECTED_SHA.slice(0, 16) + "...",
    pilot_id: "PILOT-2026-001", customer_ref: "CUST-A1", project_ref: "PILOT-2026-001-PROJ-01",
    output_profile: "vertical_9_16", duration: "30s", title: "Promo", asset_count: 3,
    assets: [], external_action_restrictions: { publishing: "NOT_AUTHORIZED" },
    delivery_method: "MANUAL_OPERATOR_HANDOFF_ONLY", font_policy: "OPEN_SOURCE_APPROVED",
  },
};

describe("paid-pilot packet-admission route (§6.A)", () => {
  it("passes admission and returns browser-safe projection", async () => {
    invokeAdmission.mockResolvedValue(PASS);
    const res = await post({ operation: "admit-packet", expected_sha256: EXPECTED_SHA });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.projection.asset_count).toBe(3);
    expect(JSON.stringify(body)).not.toMatch(/C:\\|secret|NODE_ENV/);
  });

  it("rejects missing expected_sha256 (no browser path accepted)", async () => {
    invokeAdmission.mockResolvedValue(PASS);
    const res = await post({ operation: "admit-packet" });
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("EXPECTED_SHA_REQUIRED");
  });

  it("strips browser-supplied path fields (security)", async () => {
    let captured: Record<string, unknown> | null = null;
    invokeAdmission.mockImplementation(async (_op: string, p: Record<string, unknown>) => {
      captured = p;
      return PASS;
    });
    await post({ operation: "admit-packet", expected_sha256: EXPECTED_SHA, packet_path: "/evil/x.json", approved_input_root: "/evil" });
    expect(captured).not.toHaveProperty("packet_path");
    expect(captured).not.toHaveProperty("approved_input_root");
  });

  it("forwards admission failure with no write", async () => {
    invokeAdmission.mockResolvedValue({ ok: false, error_code: "PACKET_SHA256_MISMATCH", detail: "mismatch", gates: [], assets: [], projection: null });
    const res = await post({ operation: "admit-packet", expected_sha256: "0".repeat(64) });
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.ok).toBe(false);
  });
});
