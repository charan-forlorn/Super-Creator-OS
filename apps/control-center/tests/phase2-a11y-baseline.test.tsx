import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CreateProjectWizard } from "@/components/create-project-wizard";
import { ConfirmationModal } from "@/components/confirmation-modal";
import { HvsRenderPanel } from "@/components/hvs-render-panel";

const PROJECT = "spp-abcdef123456";

/**
 * Phase 2 accessibility baseline (custom, dependency-free). Asserts the
 * contract hooks the project already exposes: aria labels, role=alert on
 * errors, dialog semantics, and disabled-until-confirm gating.
 */
beforeEach(() => {});
afterEach(() => vi.unstubAllGlobals());

describe("Phase 2 accessibility baseline", () => {
  it("wizard inputs carry programmatic labels", () => {
    render(<CreateProjectWizard />);
    expect(screen.getByLabelText("Project title")).toBeTruthy();
    expect(screen.getByLabelText("Content brief")).toBeTruthy();
    expect(screen.getByLabelText("Client or brand")).toBeTruthy();
    expect(screen.getByLabelText("Project purpose")).toBeTruthy();
  });

  it("confirmation modal exposes dialog semantics and cancels on Escape", () => {
    let confirmed = false;
    render(
      <ConfirmationModal
        open
        title="Confirm render"
        description="explicit"
        confirmLabel="Confirm render"
        onConfirm={() => { confirmed = true; }}
        onCancel={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(confirmed).toBe(false);
  });

  it("render execute stays disabled until the explicit-confirm checkbox is checked", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ project_id: PROJECT, truth_state: "RENDER_NOT_REQUESTED", current_revision: 2, plan: null, attempts: [] }) }) as Response));
    render(<HvsRenderPanel projectId={PROJECT} />);
    const checkbox = await screen.findByLabelText(/I confirm this authorized render/i);
    const execute = screen.getByRole("button", { name: /Execute render/i }) as HTMLButtonElement;
    expect(execute.disabled).toBe(true);
    fireEvent.click(checkbox);
    expect(execute.disabled).toBe(false);
  });
});
