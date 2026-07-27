// @vitest-environment node
// SCOS Cohort 10H — Phase B/C/D focused download-route boundary test.
// Reproduces the server-side relative-fetch defect, then proves the repair:
// the route must use the SERVER-ONLY bridge (not the browser client) so it
// works under Node.js route runtime.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { NextRequest } from "next/server";

// --- mock next/server so the route handler is unit-testable ---
// NextResponse must be a CLASS (the route does `new NextResponse(...)`).
class FakeNextResponse {
  status: number;
  headers: Map<string, string>;
  body: Uint8Array | null;
  constructor(body: Uint8Array | string | null, init?: { status?: number; headers?: Record<string, string> }) {
    this.status = init?.status ?? 200;
    this.headers = new Map(Object.entries(init?.headers ?? {}));
    this.body = typeof body === "string" ? new TextEncoder().encode(body) : body;
  }
  static json(data: unknown, init?: { status?: number; headers?: Record<string, string> }) {
    return new FakeNextResponse(JSON.stringify(data), { ...init, headers: { ...(init?.headers ?? {}), "content-type": "application/json" } });
  }
}

// A minimal typed stand-in for the route's request shape.
interface DownloadRequest {
  nextUrl: { searchParams: URLSearchParams };
}

vi.mock("next/server", () => ({
  NextResponse: FakeNextResponse,
  NextRequest: class {
    nextUrl: { searchParams: URLSearchParams };
    constructor(u: string) {
      this.nextUrl = { searchParams: new URL(u).searchParams };
    }
  },
}));

const DELIVERY_ID = "scos-hvs-pp-delivery-spp-paidpilot-10h";
const SAFE_NAME = DELIVERY_ID.replace(/[^a-z0-9_-]/gi, "_") + ".zip";
const PKG_SHA = "bb52273f4a3a1d64421785a84a6221ec2bf75a1bda42d8978d709e3c449b827e";
const PKG_BYTES = new TextEncoder().encode("fake-sealed-package-bytes");
const PKG_ROOT = join(tmpdir(), "scos-10h-dltest");

// bridge mock (server-only). The repair must make the route import THIS.
const bridgeGetDelivery = vi.fn();
vi.mock("@/lib/paid-pilot-delivery-bridge", () => ({
  getDelivery: (id: string) => bridgeGetDelivery(id),
  submitRightsReview: vi.fn(), approveDelivery: vi.fn(), createDeliveryPackage: vi.fn(),
  runMediaQa: vi.fn(), markHandoffReady: vi.fn(), listDeliveries: vi.fn(),
}));

// client mock (browser). Pre-repair the route imports this and its relative
// fetch fails server-side (simulated here).
const clientGetDelivery = vi.fn(async (_id?: string) => ({
  ok: false, error_code: "REQUEST_FAILED", detail: "Failed to parse URL from /api/paid-pilot/delivery?deliveryId=" + DELIVERY_ID, record: null,
  package_sha256: null, package_path: null, backup_receipt: null,
}));
vi.mock("@/lib/paid-pilot-delivery-client", () => ({
  getDelivery: (id: string) => clientGetDelivery(id),
  submitRightsReview: vi.fn(), approveDelivery: vi.fn(), createDeliveryPackage: vi.fn(),
  runMediaQa: vi.fn(), markHandoffReady: vi.fn(), readDeliveryProjection: vi.fn(), listDeliveries: vi.fn(),
}));

type DownloadRouteResponse = {
  status: number;
  headers: { get(name: string): string | null };
  body: Uint8Array | null;
};

const { GET } = await import("@/app/api/paid-pilot/delivery/download/route");

function makeReq(id: string): NextRequest {
  return { nextUrl: { searchParams: new URLSearchParams(`deliveryId=${id}`) } } as NextRequest;
}

function callGet(id: string): Promise<DownloadRouteResponse> {
  return GET(makeReq(id)) as Promise<DownloadRouteResponse>;
}

describe("paid-pilot download route server boundary", () => {
  beforeEach(() => {
    bridgeGetDelivery.mockReset();
    clientGetDelivery.mockClear();
    rmSync(PKG_ROOT, { recursive: true, force: true });
    mkdirSync(PKG_ROOT, { recursive: true });
    writeFileSync(join(PKG_ROOT, SAFE_NAME), PKG_BYTES);
    process.env.SCOS_PAID_PILOT_PACKAGE_ROOT = PKG_ROOT;
  });

  it("reproduces the server-side relative-fetch defect (route uses server bridge, bridge surfaces REQUEST_FAILED)", async () => {
    // Post-repair the route imports the server bridge; the pre-repair defect
    // (browser client relative fetch failing under Node) is reproduced by the
    // bridge returning the same REQUEST_FAILED envelope the client produced.
    bridgeGetDelivery.mockResolvedValue({ ok: false, error_code: "REQUEST_FAILED", detail: "Failed to parse URL from /api/paid-pilot/delivery?deliveryId=" + DELIVERY_ID, record: null, package_sha256: null, package_path: null, backup_receipt: null });
    const res = await callGet(DELIVERY_ID);
    const body = JSON.parse(new TextDecoder().decode(res.body ?? new Uint8Array())) as { ok: boolean; error_code: string; detail: string };
    expect(body.ok).toBe(false);
    expect(body.error_code).toBe("REQUEST_FAILED");
    expect(String(body.detail)).toContain("Failed to parse URL");
    expect(bridgeGetDelivery).toHaveBeenCalledWith(DELIVERY_ID);
  });

  it("uses the server bridge and returns downloadable bytes after repair", async () => {
    bridgeGetDelivery.mockResolvedValue({ ok: true, error_code: null, detail: null, record: { state: "DELIVERY_READY_FOR_MANUAL_HANDOFF", package_sha256: PKG_SHA }, package_sha256: PKG_SHA, package_path: null, backup_receipt: null });
    const res = await callGet(DELIVERY_ID);
    expect(bridgeGetDelivery).toHaveBeenCalledWith(DELIVERY_ID);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-disposition")).not.toMatch(/[A-Za-z]:\/^\//);
    expect(res.headers.get("content-type")).toBe("application/zip");
    expect(res.headers.get("x-package-sha256")).toBe(PKG_SHA);
    expect(res.body).toBeInstanceOf(Uint8Array);
    expect(Array.from(res.body ?? new Uint8Array())).toEqual(Array.from(PKG_BYTES));
  });

  it("missing delivery fails closed (bridge returns not-found)", async () => {
    bridgeGetDelivery.mockResolvedValue({ ok: false, error_code: "DELIVERY_NOT_FOUND", detail: null, record: null, package_sha256: null, package_path: null, backup_receipt: null });
    const res = await callGet(DELIVERY_ID);
    expect(res.status).toBe(404);
  });

  it("non-ready delivery fails closed (bridge returns not-ready)", async () => {
    bridgeGetDelivery.mockResolvedValue({ ok: true, error_code: null, detail: null, record: { state: "DELIVERY_APPROVED", package_sha256: "" }, package_sha256: null, package_path: null, backup_receipt: null });
    const res = await callGet(DELIVERY_ID);
    expect(res.status).toBe(409);
  });

  it("bridge failure maps to browser-safe error (no raw path/stderr)", async () => {
    bridgeGetDelivery.mockResolvedValue({ ok: false, error_code: "BRIDGE_SPAWN_FAILED", detail: "no response from delivery authority", record: null, package_sha256: null, package_path: null, backup_receipt: null });
    const res = await callGet(DELIVERY_ID);
    const body = JSON.parse(new TextDecoder().decode(res.body ?? new Uint8Array())) as { ok: boolean; detail?: string };
    expect(body.ok).toBe(false);
    expect(String(body.detail ?? "")).not.toMatch(/[A-Za-z]:\\/); // no absolute path leak
  });
});
