/**
 * SCOS Cohort 10H — frontend contract test for PaidPilotDeliveryPanel.
 *
 * Browser-safe projection + operator-action only. The Python authority is
 * mocked (the real bridge spawns a child process, unavailable in jsdom).
 * Verifies:
 *  - panel renders with a clear "browser is projection only" note
 *  - rights review triggers the bridge and reflects the returned rights status
 *  - approve button is disabled until rights APPROVED + QA PASSED
 *  - package button is disabled until operator decision APPROVED_FOR_DELIVERY
 *  - download button is enabled only in a ready state
 *  - no absolute path / secret / repo path is ever rendered to the DOM
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within, waitFor } from "@testing-library/react";
import { PaidPilotDeliveryPanel } from "@/components/paid-pilot-delivery-panel";
import * as bridge from "@/lib/paid-pilot-delivery-client";
import type { DeliveryRecordView, DeliveryResponse, OperatorDecision } from "@/lib/paid-pilot-types";

const RIGHTS_APPROVED: DeliveryRecordView = {
  delivery_id: "scos-hvs-pp-delivery-aaaabbbbccccdddd",
  project_id: "spp-paidpilot-10h",
  source_render_attempt_id: "a1",
  artifact_identity: "art1",
  artifact_sha256: "a".repeat(64),
  artifact_size: 2048,
  media_profile: "vertical_9_16",
  qa_record_id: "q1",
  qa_state: "QA_PASSED",
  operator_id: "local-solo-operator",
  operator_decision: "APPROVAL_REQUIRED",
  rights_checklist_revision: "r1",
  rights_status: "RIGHTS_APPROVED",
  package_revision: "",
  package_sha256: "",
  backup_receipt: null,
  retention_class: "MANUAL_PURGE_REQUIRED",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
  state: "DELIVERY_AWAITING_OPERATOR_APPROVAL",
};

type BridgeMock = (...args: unknown[]) => Promise<DeliveryResponse>;
function mockBridge(overrides: Partial<Record<string, BridgeMock>> = {}) {
  // Faithful mini-authority: the projection and reads reflect the latest approved
  // transition, mirroring the real Python store that the panel re-reads via refresh().
  let current: DeliveryRecordView = { ...RIGHTS_APPROVED };
  const submitRightsReview = vi.fn(async (...args: unknown[]) => {
    const [opts] = args as [{ deliveryId: string }];
    current = { ...current, delivery_id: opts.deliveryId, rights_status: "RIGHTS_APPROVED", operator_decision: "APPROVAL_REQUIRED", state: "DELIVERY_AWAITING_OPERATOR_APPROVAL" };
    return { ok: true, error_code: null, detail: null, record: { ...current }, package_sha256: null, package_path: null, backup_receipt: null };
  });
  const approveDelivery = vi.fn(async (...args: unknown[]) => {
    const [opts] = args as [{ decision: OperatorDecision }];
    current = { ...current, operator_decision: opts.decision, state: opts.decision === "APPROVED_FOR_DELIVERY" ? "DELIVERY_APPROVED" : "DELIVERY_REJECTED" };
    return { ok: true, error_code: null, detail: null, record: { ...current }, package_sha256: null, package_path: null, backup_receipt: null };
  });
  const createDeliveryPackage = vi.fn(async () => {
    current = {
      ...current,
      operator_decision: "APPROVED_FOR_DELIVERY",
      state: "DELIVERY_READY_FOR_MANUAL_HANDOFF",
      package_sha256: "b".repeat(64),
    };
    return {
      ok: true, error_code: null, detail: null, record: { ...current },
      package_sha256: "b".repeat(64), package_path: null,
      backup_receipt: { backup_id: "bk1", package_id: current.delivery_id, package_sha256: "b".repeat(64), backup_sha256: "b".repeat(64), created_at: "2026-07-21T00:00:00Z", protection_class: "SINGLE_DISK_DUAL_ROOT_NO_CLOUD" },
    };
  });
  const markHandoffReady = vi.fn(async () => ({
    ok: true, error_code: null, detail: null,
    record: { ...current, state: "DELIVERY_READY_FOR_MANUAL_HANDOFF" },
    package_sha256: "b".repeat(64), package_path: null, backup_receipt: null,
  }));
  const readDeliveryProjection = vi.fn(async () => ({ status: "AVAILABLE_WITH_DATA" as const, record: { ...current } }));
  const getDelivery = vi.fn(async () => ({ ok: true, error_code: null, detail: null, record: { ...current }, package_sha256: null, package_path: null, backup_receipt: null }));
  const listDeliveries = vi.fn(async () => ({ ok: true, error_code: null, detail: null, record: null, package_sha256: null, package_path: null, backup_receipt: null }));
  return Object.assign(
    { submitRightsReview, approveDelivery, createDeliveryPackage, markHandoffReady, readDeliveryProjection, getDelivery, listDeliveries },
    overrides,
  );
}

describe("PaidPilotDeliveryPanel (browser-safe projection)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders with projection-only note and no leak of paths/secrets", () => {
    const mocks = mockBridge();
    vi.spyOn(bridge, "submitRightsReview").mockImplementation(mocks.submitRightsReview);
    vi.spyOn(bridge, "readDeliveryProjection").mockImplementation(mocks.readDeliveryProjection);
    vi.spyOn(bridge, "getDelivery").mockImplementation(mocks.getDelivery);
    vi.spyOn(bridge, "listDeliveries").mockImplementation(mocks.listDeliveries);
    render(<PaidPilotDeliveryPanel />);
    expect(screen.getByText(/Durable, no-terminal delivery ownership/i)).toBeTruthy();
    expect(screen.getByText(/Browser is projection only/i)).toBeTruthy();
    const body = document.body.textContent || "";
    expect(body).not.toMatch(/C:\\|\\\\|\/Users\/|\/workspace\//i);
    expect(body).not.toMatch(/SCOS_PYTHON_INTERPRETER|secret|token|password/i);
  });

  it("rights review enables the approve action only when APPROVED + QA PASSED", async () => {
    const mocks = mockBridge();
    vi.spyOn(bridge, "submitRightsReview").mockImplementation(mocks.submitRightsReview);
    vi.spyOn(bridge, "readDeliveryProjection").mockImplementation(mocks.readDeliveryProjection);
    vi.spyOn(bridge, "getDelivery").mockImplementation(mocks.getDelivery);
    vi.spyOn(bridge, "listDeliveries").mockImplementation(mocks.listDeliveries);
    render(<PaidPilotDeliveryPanel />);
    const approveBtn = screen.getByRole("button", { name: /Approve for delivery/i }) as HTMLButtonElement;
    // Before rights review, not APPROVED_PAIR -> disabled.
    expect(approveBtn.disabled).toBe(true);
    await fireEvent.click(screen.getByRole("button", { name: /Submit rights review/i }));
    expect(mocks.submitRightsReview).toHaveBeenCalledTimes(1);
    // rights APPROVED + QA_PASSED -> approve enabled (async state transition).
    await waitFor(() =>
      expect((screen.getByRole("button", { name: /Approve for delivery/i }) as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it("package button gated until APPROVED_FOR_DELIVERY; download gated until ready", async () => {
    const mocks = mockBridge();
    vi.spyOn(bridge, "submitRightsReview").mockImplementation(mocks.submitRightsReview);
    vi.spyOn(bridge, "approveDelivery").mockImplementation(mocks.approveDelivery);
    vi.spyOn(bridge, "createDeliveryPackage").mockImplementation(mocks.createDeliveryPackage);
    vi.spyOn(bridge, "readDeliveryProjection").mockImplementation(mocks.readDeliveryProjection);
    vi.spyOn(bridge, "getDelivery").mockImplementation(mocks.getDelivery);
    vi.spyOn(bridge, "listDeliveries").mockImplementation(mocks.listDeliveries);
    render(<PaidPilotDeliveryPanel />);
    await fireEvent.click(screen.getByRole("button", { name: /Submit rights review/i }));
    const approveBtn = () => screen.getByRole("button", { name: /Approve for delivery/i }) as HTMLButtonElement;
    const pkgBtn = () => screen.getByRole("button", { name: /Generate package/i }) as HTMLButtonElement;
    const dlBtn = () => screen.getByRole("button", { name: /Download package/i }) as HTMLButtonElement;
    // After rights review the record (RIGHTS_APPROVED + QA_PASSED) arrives asynchronously;
    // the approve action becomes enabled.
    await waitFor(() => expect(approveBtn()).toBeEnabled());
    // rights approved but not yet operator-approved -> package + download disabled.
    await waitFor(() => expect(pkgBtn()).toBeDisabled());
    await waitFor(() => expect(dlBtn()).toBeDisabled());
    await fireEvent.click(approveBtn());
    await waitFor(() => expect(mocks.approveDelivery).toHaveBeenCalledTimes(1));
    // now package enabled, download still blocked (no package yet).
    await waitFor(() => expect(pkgBtn()).toBeEnabled());
    await waitFor(() => expect(dlBtn()).toBeDisabled());
    await fireEvent.click(pkgBtn());
    await waitFor(() => expect(mocks.createDeliveryPackage).toHaveBeenCalledTimes(1));
    // ready -> download enabled.
    await waitFor(() => expect(dlBtn()).toBeEnabled());
  });
});
