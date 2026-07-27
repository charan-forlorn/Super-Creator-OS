// @vitest-environment node
// SCOS Cohort 10I — paid-pilot readiness route contract test.
// Verifies the readiness projection endpoint is browser-safe, delegates to the
// authoritative Python readiness authority (no client-side derivation), and
// never leaks absolute paths, secrets, or raw stderr.
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { NextRequest } from "next/server";

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

interface ReadinessRequest {
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

const DELIVERY_ID = "scos-hvs-pp-delivery-spp-paidpilot-10i";

// The route delegates to the authoritative Python readiness projection.
const bridgeGetReadiness = vi.fn();
vi.mock("@/lib/paid-pilot-delivery-bridge", () => ({
  getReadiness: (id: string) => bridgeGetReadiness(id),
  getDelivery: vi.fn(), submitRightsReview: vi.fn(), approveDelivery: vi.fn(),
  createDeliveryPackage: vi.fn(), runMediaQa: vi.fn(), markHandoffReady: vi.fn(),
  listDeliveries: vi.fn(),
}));

type ReadinessResponse = {
  status: number;
  headers: { get(name: string): string | null };
  body: Uint8Array | null;
};

const { GET } = await import("@/app/api/paid-pilot/readiness/route");

function makeReq(id: string): NextRequest {
  return { nextUrl: { searchParams: new URLSearchParams(`deliveryId=${id}`) } } as NextRequest;
}

function callGet(id: string): Promise<ReadinessResponse> {
  return GET(makeReq(id)) as Promise<ReadinessResponse>;
}

function parse(res: ReadinessResponse) {
  return JSON.parse(new TextDecoder().decode(res.body ?? new Uint8Array())) as Record<string, unknown>;
}

describe("paid-pilot readiness route", () => {
  beforeEach(() => {
    bridgeGetReadiness.mockReset();
  });

  it("rejects malformed delivery id", async () => {
    const res = await callGet("../evil");
    expect(res.status).toBe(400);
    const body = parse(res) as { error_code: string };
    expect(body.error_code).toBe("DELIVERY_ID_MALFORMED");
  });

  it("returns NOT_READY when authority reports no record", async () => {
    bridgeGetReadiness.mockResolvedValue({
      ok: false, error_code: "DELIVERY_NOT_FOUND", detail: null, record: null,
      package_sha256: null, package_path: null, backup_receipt: null,
    });
    const res = await callGet(DELIVERY_ID);
    expect(res.status).toBe(200);
    const body = parse(res) as { state: string; ok: boolean };
    expect(body.ok).toBe(true);
    expect(body.state).toBe("NOT_READY");
  });

  it("faithfully returns the authoritative BLOCKED projection", async () => {
    bridgeGetReadiness.mockResolvedValue({
      ok: true, record: { state: "DELIVERY_PACKAGE_CORRUPT" },
      state: "BLOCKED", delivery_id: DELIVERY_ID,
      checks: [{ name: "delivery_record", passed: false, reason_code: "DELIVERY_BLOCKED", detail: "state=DELIVERY_PACKAGE_CORRUPT" }],
      blocking_reasons: ["DELIVERY_BLOCKED"],
      package_sha256: null, backup_sha256: null, audit_sha256: null,
    });
    const res = await callGet(DELIVERY_ID);
    const body = parse(res) as { state: string };
    expect(body.state).toBe("BLOCKED");
  });

  it("faithfully returns the authoritative READY_FOR_CONTROLLED_PILOT projection", async () => {
    bridgeGetReadiness.mockResolvedValue({
      ok: true, record: { state: "DELIVERY_READY_FOR_MANUAL_HANDOFF" },
      state: "READY_FOR_CONTROLLED_PILOT", delivery_id: DELIVERY_ID,
      checks: [
        { name: "store_integrity", passed: true, reason_code: "STORE_OK", detail: "ok" },
        { name: "delivery_record", passed: true, reason_code: "DELIVERY_RECORD_OK", detail: "ok" },
        { name: "rights_review", passed: true, reason_code: "RIGHTS_APPROVED", detail: "ok" },
        { name: "qa_status", passed: true, reason_code: "QA_PASSED", detail: "ok" },
        { name: "operator_approval", passed: true, reason_code: "APPROVED", detail: "ok" },
        { name: "package_integrity", passed: true, reason_code: "PACKAGE_OK", detail: "ok" },
        { name: "backup_integrity", passed: true, reason_code: "BACKUP_OK", detail: "ok" },
        { name: "restore_drill", passed: true, reason_code: "RESTORE_VERIFIED", detail: "ok" },
        { name: "audit_integrity", passed: true, reason_code: "AUDIT_OK", detail: "ok" },
        { name: "security_truth_canonical", passed: true, reason_code: "GATES_PASS", detail: "ok" },
      ],
      blocking_reasons: [],
      package_sha256: "b".repeat(64), backup_sha256: "b".repeat(64), audit_sha256: "a".repeat(64),
    });
    const res = await callGet(DELIVERY_ID);
    const body = parse(res) as { state: string; checks: unknown[] };
    expect(body.state).toBe("READY_FOR_CONTROLLED_PILOT");
    expect(body.checks.length).toBeGreaterThanOrEqual(8);
  });

  it("never leaks absolute paths, secrets, or raw stderr", async () => {
    bridgeGetReadiness.mockResolvedValue({
      ok: true, record: { state: "DELIVERY_READY_FOR_MANUAL_HANDOFF" },
      state: "READY_FOR_CONTROLLED_PILOT", delivery_id: DELIVERY_ID,
      checks: [{ name: "store_integrity", passed: true, reason_code: "STORE_OK", detail: "ok" }],
      blocking_reasons: [],
      package_sha256: null, backup_sha256: null, audit_sha256: null,
    });
    const res = await callGet(DELIVERY_ID);
    const bodyStr = new TextDecoder().decode(res.body ?? new Uint8Array());
    expect(bodyStr).not.toMatch(/[A-Z]:\\\\/);
    expect(bodyStr).not.toMatch(/\/workspace\//i);
    expect(bodyStr).not.toMatch(/secret|password|token/i);
    expect(bodyStr).not.toMatch(/Traceback|Error:|stderr/i);
  });
});
