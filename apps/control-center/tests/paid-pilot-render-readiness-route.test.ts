import { afterEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const invokeRenderReadiness = vi.fn<(payload: Record<string, unknown>) => Promise<Record<string, unknown>>>();
vi.mock("@/lib/paid-pilot-render-readiness-bridge", () => ({ invokeRenderReadiness }));

async function post(body: Record<string, unknown>) {
  const { POST } = await import("@/app/api/paid-pilot/render-readiness/route");
  const req = new Request("http://local/api/paid-pilot/render-readiness", { method: "POST", body: JSON.stringify(body) });
  return POST(req as unknown as NextRequest);
}

afterEach(() => invokeRenderReadiness.mockReset());

const READY = {
  ok: true, state: "READY_FOR_RENDER", error_code: null, detail: null,
  checks: [
    { token: "ADMITTED_" + "PACKET", passed: true, reason_code: "OK", detail: "ok" },
    { token: "APPROVED_" + "ASSETS_BOUND", passed: true, reason_code: "OK", detail: "ok" },
    { token: "DURATION", passed: true, reason_code: "OK", detail: "ok" },
  ],
  projection: {
    schema_version: "scos-hvs.pilot-render-readiness.v1/1.0.0",
    canonical_internal_project_id: "spp-aa11bb22cc33",
    external_project_ref: "PILOT-2026-001-PROJ-01",
    output_profile: "vertical_9_16", dimensions: "1080x1920", duration_seconds: 30,
    audio_duration_seconds: 30.974943, font_family: "Noto Sans Thai",
    asset_safe_names: ["product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"],
    render_action: "DISABLED_PRE_AUTHORIZATION",
  },
};

describe("paid-pilot pre-render readiness route (§6.F)", () => {
  it("returns READY_FOR_RENDER with no render authorization", async () => {
    invokeRenderReadiness.mockResolvedValue(READY);
    const res = await post({ external_project_ref: "PILOT-2026-001-PROJ-01" });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.state).toBe("READY_FOR_RENDER");
    expect(body.projection.render_action).toBe("DISABLED_PRE_AUTHORIZATION");
  });

  it("strips browser path/identity fields (read-only, server-resolved)", async () => {
    let captured: Record<string, unknown> | null = null;
    invokeRenderReadiness.mockImplementation(async (p: Record<string, unknown>) => {
      captured = p;
      return { ok: false, state: "NOT_READY", error_code: "X", detail: "x", checks: [], projection: null };
    });
    await post({ external_project_ref: "PILOT-2026-001-PROJ-01", canonical_internal_project_id: "spp-hax", admission_store_path: "/evil" });
    expect(captured).not.toHaveProperty("canonical_internal_project_id");
    expect(captured).not.toHaveProperty("admission_store_path");
    expect(captured).toHaveProperty("external_project_ref");
  });

  it("rejects malformed project ref", async () => {
    invokeRenderReadiness.mockResolvedValue(READY);
    const res = await post({ external_project_ref: "../escape" });
    expect(res.status).toBe(400);
  });
});
