import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";

import { HvsRenderPanel } from "@/components/hvs-render-panel";

const PROJECT = "spp-abcdef123456";
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
  truth_state: "RENDER_NOT_REQUESTED" as const,
  current_revision: null,
  plan: {
    plan_schema_version: 1,
    project_id: PROJECT,
    project_revision: 1,
    hvs_project_name: "hvs-abcdef123456",
    output_root_identity: "isolated-render-root",
    profile_metadata: { hvs_project_name: "hvs-abcdef123456" },
    expected_output_filename: "hvs-abcdef123456.vertical.h264.mp4",
    expected_output_relative_path: "render/hvs-abcdef123456/hvs-abcdef123456.vertical.h264.mp4",
    forbidden_operations: ["publish", "upload", "render-hyperframes"],
    plan_hash: PLAN_HASH,
  },
  attempts: [],
  authorization: {
    authorization_id: "auth-1",
    project_id: PROJECT,
    project_revision: 1,
    operation: "RENDER_HVS_PROJECT",
    materialization_attempt_id: "mat-1",
    render_profile_id: "vertical",
    render_plan_hash: PLAN_HASH,
    output_root_identity: "isolated-render-root",
    decision: "AUTHORIZED",
    capability_id: "cap-1",
    attempt_id: "att-1",
  },
};

function successProjection(extra: Record<string, unknown> = {}) {
  return {
    project_id: PROJECT,
    truth_state: "RENDER_SUCCEEDED" as const,
    current_revision: 2,
    plan: EMPTY_PROJECTION.plan,
    attempts: [
      {
        attempt_id: "att-1",
        project_id: PROJECT,
        project_revision: 2,
        materialization_attempt_id: "mat-1",
        materialization_plan_hash: PLAN_HASH,
        render_profile_id: "vertical",
        render_plan_hash: PLAN_HASH,
        authorization_id: "auth-1",
        capability_id: "cap-1",
        output_root_identity: "isolated-render-root",
        state: "RENDER_SUCCEEDED",
        hvs_calls: 1,
        render_calls: 1,
        created_at: "2026-07-17T00:00:00.000Z",
        updated_at: "2026-07-17T00:00:01.000Z",
        started_at: "2026-07-17T00:00:00.000Z",
        finished_at: "2026-07-17T00:00:01.000Z",
        reconciliation_count: 0,
        outcome: "success",
        error_code: null,
        error_detail: null,
        artifact_descriptor: {
          artifact_id: "a1",
          render_attempt_id: "att-1",
          profile_id: "vertical",
          filename: "hvs-abcdef123456.vertical.h264.mp4",
          media_type: "video/mp4",
          size_bytes: 12345,
          sha256: "deadbeef" + "0".repeat(56),
          duration: 3.0,
          width: 1080,
          height: 1920,
          frame_rate: 30,
          video_codec: "h264",
          audio_codec: null,
          validation_state: "VERIFIED",
        },
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
      if (url === "/api/hvs-render/authorize" && method === "POST") {
        payload = activePlan.authorize ? activePlan.authorize(body) : { ok: true, decision: "AUTHORIZED" };
      } else if (url === "/api/hvs-render/execute" && method === "POST") {
        payload = activePlan.execute ? activePlan.execute(body) : { ok: true, result: { ok: true, state: "RENDER_SUCCEEDED", attempt_id: "att-1", render_calls: 1, outcome: "success" } };
      } else if (url === "/api/hvs-render/reconcile" && method === "POST") {
        payload = activePlan.reconcile ? activePlan.reconcile(body) : { ok: true, classification: "STILL_UNKNOWN" };
      }
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

describe("HvsRenderPanel — truth states + controls", () => {
  it("shows NOT_REQUESTED with the deterministic plan before authorization (req 1)", async () => {
    activePlan = { projection: () => EMPTY_PROJECTION };
    render(<HvsRenderPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getAllByText(/RENDER_NOT_REQUESTED/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/Deterministic render plan/i)).toBeInTheDocument();
    expect(screen.getByText(/No render starts automatically/i)).toBeInTheDocument();
  });

  it("refresh restores the persisted rendered outcome (req 7)", async () => {
    activePlan = { projection: () => successProjection() };
    render(<HvsRenderPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getAllByText(/RENDER_SUCCEEDED/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/Validated artifact/i)).toBeInTheDocument();
  });

  it("requires explicit confirmation before rendering (req 3)", async () => {
    let executed = false;
    activePlan = {
      projection: () => ({ ...EMPTY_PROJECTION, truth_state: "RENDER_AUTHORIZED" }),
      authorize: () => ({ ok: true, decision: "AUTHORIZED" }),
      execute: () => {
        executed = true;
        return { ok: true, result: { ok: true, state: "RENDER_SUCCEEDED", attempt_id: "att-1", render_calls: 1, outcome: "success" } };
      },
    };
    render(<HvsRenderPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Execute render/i })).toBeInTheDocument());
    const renderBtn = screen.getByRole("button", { name: /Execute render/i });
    // Execute is reachable once authorized; the explicit confirm is enforced inside the modal.
    expect(renderBtn).toBeEnabled();
    fireEvent.click(renderBtn);
    const dialog = await screen.findByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", { name: /Confirm render/i }) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Explicitly confirm/i));
    await waitFor(() => expect(confirmBtn).toBeEnabled());
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(executed).toBe(true));
  });

  it("does not use browser storage and keeps controls usable on narrow containers (req 12/14)", async () => {
    activePlan = { projection: () => EMPTY_PROJECTION };
    const { container } = render(<HvsRenderPanel projectId={PROJECT} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Request render authorization/i })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Request render authorization/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Execute render/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reconcile/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Explicitly confirm/i)).toBeInTheDocument();
    const controls = container.querySelector(".flex-wrap");
    expect(controls).not.toBeNull();
  });
});
