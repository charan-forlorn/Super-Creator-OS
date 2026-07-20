import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CreateProjectWizard } from "@/components/create-project-wizard";
import { HvsRenderPanel } from "@/components/hvs-render-panel";
import { ConfirmationModal } from "@/components/confirmation-modal";

/**
 * Phase 2 — Golden Project happy path (test-double at the fetch boundary).
 * Drives the real components through jsdom; no real Python, no network.
 */
const PROJECT = "spp-abcdef123456";
const PLAN_HASH = "a".repeat(64);

function installFetch(overrides: Record<string, unknown> = {}) {
  const projection = {
    project_id: PROJECT,
    truth_state: "RENDER_AUTHORIZED" as const,
    current_revision: 2,
    plan: {
      plan_schema_version: 1,
      project_id: PROJECT,
      project_revision: 1,
      hvs_project_name: "hvs-abcdef123456",
      output_root_identity: "OUT",
      profile_metadata: { hvs_project_name: "hvs-abcdef123456" },
      expected_output_filename: "out.mp4",
      expected_output_relative_path: "render/out.mp4",
      forbidden_operations: ["publish", "upload", "render-hyperframes"],
      plan_hash: PLAN_HASH,
    },
    authorization: {
      authorization_id: "auth-1",
      capability_id: "cap-1",
      attempt_id: "att-1",
      project_id: PROJECT,
      project_revision: 1,
      operation: "RENDER_HVS_PROJECT",
      materialization_attempt_id: "mat-1",
      render_profile_id: "vertical",
      render_plan_hash: PLAN_HASH,
      output_root_identity: "isolated-render-root",
      decision: "AUTHORIZED",
    },
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
        output_root_identity: "OUT",
        state: "RENDER_SUCCEEDED",
        hvs_calls: 1,
        render_calls: 1,
        outcome: "success",
        error_code: null,
        artifact_descriptor: { filename: "out.mp4", sha256: "deadbeef", validation_state: "VERIFIED" },
      },
    ],
  };

  const handler = (url: string) => {
    if (url.includes("/api/hvs-render/projection")) {
      return { ok: true, json: async () => projection };
    }
    if (url.includes("/api/hvs-render/execute")) {
      return { ok: true, json: async () => ({ ok: true, state: "RENDER_SUCCEEDED", attempt_id: "att-1", outcome: "success" }) };
    }
    if (url.includes("/api/hvs-render/export")) {
      return { ok: true, json: async () => ({ ok: true, download_url: "data:application/json;base64,xxx", sha256: "abc" }) };
    }
    if (url.includes("/api/project-preparation")) {
      return {
        ok: true,
        json: async () => ({
          ok: true,
          record: {
            project_id: "spp-abcdef123456",
            state: "APPROVAL_REQUIRED",
            normalized: { normalized_brief_summary: "demo brief", planned_rendition_count: 1, output_profiles: [] },
          },
        }),
      };
    }
    return { ok: true, json: async () => ({ status: "EMPTY", records: [] }) };
  };

  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    return handler(url) as Response;
  });
  vi.stubGlobal("fetch", stub as unknown as typeof fetch);
  Object.assign(overrides, { stub });
}

beforeEach(() => installFetch());
afterEach(() => vi.unstubAllGlobals());

describe("Phase 2 Golden Project happy path", () => {
  it("creates a draft through the wizard, then renders with explicit confirmation", async () => {
    render(<CreateProjectWizard />);
    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: "Golden Demo" } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: "A short promo" } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: "ACME" } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: "Promote" } });
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Create draft/i }));
    expect(await screen.findByText(/Draft created/i)).toBeTruthy();

    // Render panel — explicit confirmation gating.
    const { unmount } = render(<HvsRenderPanel projectId={PROJECT} />);
    const checkbox = await screen.findByLabelText(/I confirm this authorized render/i);
    expect((checkbox as HTMLInputElement).disabled).toBe(false);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /Execute render/i }));
    // Modal opens; final confirm is the only execute path.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Confirm render/i }));
    // Execute request actually fired against the real API boundary.
    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as { mock?: { calls: unknown[][] } }).mock?.calls ?? [];
      expect(calls.some((c) => String(c[0]).includes("/api/hvs-render/execute"))).toBe(true);
    });
    unmount();
  });

  it("ConfirmationModal cancels on Escape without executing", () => {
    let confirmed = false;
    render(
      <ConfirmationModal
        open
        title="Confirm"
        description="desc"
        confirmLabel="Go"
        onConfirm={() => { confirmed = true; }}
        onCancel={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(confirmed).toBe(false);
  });
});
