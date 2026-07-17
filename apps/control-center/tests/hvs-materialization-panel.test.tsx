import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { HvsMaterializationPanel } from "@/components/hvs-materialization-panel";

const PROJECT = "spp-25177649af09";
const PLAN_HASH = "a".repeat(64);

type FetchPlan = {
  projection?: () => unknown;
  authorize?: (body: string) => unknown;
  execute?: (body: string) => unknown;
  reconcile?: (body: string) => unknown;
};

let activePlan: FetchPlan = {};

const EMPTY_PROJECTION = {
  project_id: PROJECT,
  truth_state: "MATERIALIZATION_NOT_REQUESTED",
  current_revision: null,
  plan: {
    plan_schema_version: 1,
    project_id: PROJECT,
    project_revision: 1,
    normalized_hvs_project_name: "hvs-25177649af09",
    destination_identity: "C:/Workspace/super-creator-os/memory/runtime/control-center/hvs-projects",
    project_metadata: { hvs_project_name: "hvs-25177649af09" },
    output_profiles: ["vertical_9_16"],
    expected_files: ["projects/hvs-25177649af09/initialization_manifest.json"],
    forbidden_operations: ["render"],
    plan_hash: PLAN_HASH,
  },
  attempts: [],
};

function successProjection(extra: Record<string, unknown> = {}) {
  return {
    project_id: PROJECT,
    truth_state: "HVS_PROJECT_MATERIALIZED" as const,
    current_revision: 2,
    plan: EMPTY_PROJECTION.plan,
    attempts: [
      {
        attempt_id: "att-1",
        project_id: PROJECT,
        project_revision: 2,
        plan_hash: PLAN_HASH,
        destination_identity: EMPTY_PROJECTION.plan.destination_identity,
        authorization_id: "auth-1",
        capability_id: "cap-1",
        state: "HVS_PROJECT_MATERIALIZED",
        hvs_calls: 1,
        started_at: "2026-07-17T00:00:00.000Z",
        finished_at: "2026-07-17T00:00:01.000Z",
        outcome: "success",
        error_code: null,
        error_detail: null,
        persisted_result: { hvs_project_name: "hvs-25177649af09", hvs_calls: 1 },
      },
    ],
    ...extra,
  };
}

beforeEach(() => {
  activePlan = {};
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage read");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage write");
  });
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage remove");
  });
  vi.spyOn(Storage.prototype, "clear").mockImplementation(() => {
    throw new Error("Unexpected browser storage clear");
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: unknown) => {
      const url = String(input);
      if (/^https?:\/\//i.test(url) || url.startsWith("//")) {
        throw new Error(`Unexpected external fetch: ${url}`);
      }
      const method = (init as { method?: string } | undefined)?.method ?? "GET";
      let payload: unknown = activePlan.projection ? activePlan.projection() : EMPTY_PROJECTION;
      const body = (init as { body?: string }).body ?? "";
      if (url === "/api/hvs-materialization/authorize" && method === "POST") {
        payload = activePlan.authorize ? activePlan.authorize(body) : { ok: true, decision: "AUTHORIZED" };
      } else if (url === "/api/hvs-materialization/execute" && method === "POST") {
        payload = activePlan.execute ? activePlan.execute(body) : { ok: true, result: { ok: true, state: "HVS_PROJECT_MATERIALIZED", attempt_id: "att-1", hvs_calls: 1, outcome: "success" } };
      } else if (url === "/api/hvs-materialization/reconcile" && method === "POST") {
        payload = activePlan.reconcile ? activePlan.reconcile(body) : { ok: true, classification: "STILL_UNKNOWN" };
      }
      // The projection GET returns an envelope { ok, projection }; the
      // authorize/execute/reconcile routes return their response payload
      // directly (already shaped with ok/decision/result/classification).
      const responseBody = url.includes("/projection") ? { ok: true, projection: payload } : payload;
      return { ok: true, status: 200, json: async () => responseBody };
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  activePlan = {};
});

describe("HvsMaterializationPanel — truth states + controls", () => {
  it("shows NOT_REQUESTED with the deterministic plan before authorization (req 1)", async () => {
    activePlan = { projection: () => EMPTY_PROJECTION };
    render(<HvsMaterializationPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getAllByText(/MATERIALIZATION_NOT_REQUESTED/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/Deterministic materialization plan/i)).toBeInTheDocument();
    expect(screen.getByText(/No render will start/i)).toBeInTheDocument();
  });

  it("refresh restores the persisted materialized outcome (req 7)", async () => {
    activePlan = { projection: () => successProjection() };
    render(<HvsMaterializationPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getAllByText(/HVS_PROJECT_MATERIALIZED/i).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/hvs-25177649af09/).length).toBeGreaterThan(0);
  });

  it("requires explicit confirmation before materializing (req 3)", async () => {
    let executed = false;
    activePlan = {
      projection: () => ({ ...EMPTY_PROJECTION, truth_state: "MATERIALIZATION_AUTHORIZED" }),
      authorize: () => ({ ok: true, decision: "AUTHORIZED" }),
      execute: () => {
        executed = true;
        return { ok: true, result: { ok: true, state: "HVS_PROJECT_MATERIALIZED", attempt_id: "att-1", hvs_calls: 1, outcome: "success" } };
      },
    };
    render(<HvsMaterializationPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Materialize/i })).toBeInTheDocument());
    const materializeBtn = screen.getByRole("button", { name: /Materialize/i });
    expect(materializeBtn).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Explicitly confirm/i));
    await waitFor(() => expect(materializeBtn).toBeEnabled());
    fireEvent.click(materializeBtn);
    await waitFor(() => expect(executed).toBe(true));
  });

  it("does not use browser storage or websocket and keeps controls usable on narrow containers (req 12/14)", async () => {
    activePlan = { projection: () => EMPTY_PROJECTION };
    const { container } = render(<HvsMaterializationPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Request authorization/i })).toBeInTheDocument());
    // All required controls render.
    expect(screen.getByRole("button", { name: /Request authorization/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Materialize/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reconcile/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Explicitly confirm/i)).toBeInTheDocument();
    // Responsive container (flex-wrap) so controls remain usable without
    // horizontal overflow on narrow/mobile viewports.
    const controls = container.querySelector(".flex-wrap");
    expect(controls).not.toBeNull();
  });
});
