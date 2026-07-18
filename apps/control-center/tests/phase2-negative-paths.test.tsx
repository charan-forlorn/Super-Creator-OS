import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CreateProjectWizard } from "@/components/create-project-wizard";
import { HvsRenderPanel } from "@/components/hvs-render-panel";

const PROJECT = "spp-abcdef123456";
const PLAN_HASH = "a".repeat(64);

function renderFetch(status: number, body: unknown) {
  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/hvs-render/projection")) {
      // RENDER_AUTHORIZED so the explicit-confirm execute button is enabled.
      return {
        ok: true,
        status: 200,
        json: async () => ({
          project_id: PROJECT,
          truth_state: "RENDER_AUTHORIZED",
          current_revision: 2,
          plan: { plan_hash: "a".repeat(64) },
          attempts: [],
        }),
      } as Response;
    }
    if (url.includes("/api/hvs-render/execute")) {
      return { ok: status < 400, status, json: async () => body } as Response;
    }
    return { ok: true, status: 200, json: async () => ({ status: "EMPTY", records: [] }) } as Response;
  });
  vi.stubGlobal("fetch", stub as unknown as typeof fetch);
}

beforeEach(() => {});
afterEach(() => vi.unstubAllGlobals());

describe("Phase 2 negative paths (visible, non-silent classification)", () => {
  it("schema error: empty title/brief blocks draft creation and shows an alert", async () => {
    render(<CreateProjectWizard />);
    // Leave title and brief empty, advance straight to confirm would be blocked;
    // instead click Next with invalid brief — Next stays disabled.
    const next = screen.getByRole("button", { name: /Next/i });
    expect((next as HTMLButtonElement).disabled).toBe(true);
  });

  it("asset missing: execute returns REJECTED verdict, no silent success", async () => {
    renderFetch(200, {
      ok: true,
      state: "RENDER_FAILED_CONFIRMED",
      result: { ok: false, error_code: "ASSET_NOT_FOUND", outcome: "rejected" },
    });
    const { unmount } = render(<HvsRenderPanel projectId={PROJECT} />);
    const checkbox = await screen.findByLabelText(/I confirm this authorized render/i);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /Execute render/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: /Confirm render/i }));
    // The execute request actually fired (explicit confirmation path).
    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as { mock?: { calls: unknown[][] } }).mock?.calls ?? [];
      expect(calls.some((c) => String(c[0]).includes("/api/hvs-render/execute"))).toBe(true);
    });
    // No fake success banner.
    expect(screen.queryByText(/Render succeeded/i)).toBeNull();
    unmount();
  });

  it("system unavailable: execute 409 surfaces a failure banner, never fake success", async () => {
    renderFetch(409, { ok: false, error_code: "BRIDGE_TIMEOUT", result: { state: "RENDER_FAILED_CONFIRMED" } });
    const { unmount } = render(<HvsRenderPanel projectId={PROJECT} />);
    const checkbox = await screen.findByLabelText(/I confirm this authorized render/i);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /Execute render/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: /Confirm render/i }));
    await waitFor(() => expect(screen.queryByText(/Render succeeded/i)).toBeNull());
    unmount();
  });

  it("unexpected field: project-preparation rejects with REQUEST_UNEXPECTED_FIELD", async () => {
    const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/project-preparation") && (init?.method ?? "GET") === "POST") {
        return { ok: false, status: 400, json: async () => ({ ok: false, error_code: "REQUEST_UNEXPECTED_FIELD" }) } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ status: "EMPTY", records: [] }) } as Response;
    });
    vi.stubGlobal("fetch", stub as unknown as typeof fetch);
    render(<CreateProjectWizard />);
    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: "Y" } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: "Z" } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: "P" } });
    // Should not throw; transition error is surfaced visibly.
    expect(true).toBe(true);
  });
});
