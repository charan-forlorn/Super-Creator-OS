import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { OperatorDryRunPanel } from "@/components/operator-dry-run-panel";
import { AppShell } from "@/components/app-shell";
import { buildDryRunRequest, planOperatorDryRun } from "@/lib/operator-dry-run";

describe("operator dry-run contracts", () => {
  it("accepts valid inspect requests and rejects dry_run=false", () => {
    const ready = planOperatorDryRun(buildDryRunRequest("inspect-project", { project_id: "demo-project" }));
    expect(ready.status).toBe("READY");
    expect(ready.mode).toBe("DRY_RUN");
    expect(ready.side_effects_performed).toBe(false);

    const invalid = planOperatorDryRun({ ...buildDryRunRequest("inspect-project", { project_id: "demo-project" }), dry_run: false });
    expect(invalid.status).toBe("INVALID");
    expect(invalid.reason_codes).toContain("DRY_RUN_MUST_BE_TRUE");
  });

  it("matches the backend contract when authorization evaluator input is unavailable", () => {
    for (const operation of ["initialize-project", "prepare-render"] as const) {
      const response = planOperatorDryRun(buildDryRunRequest(operation, operation === "initialize-project"
        ? { project_id: "demo-project", title: "Demo", language: "en" }
        : { project_id: "demo-project", render_profile: "vertical" }));

      expect(response.status).toBe("UNAVAILABLE");
      expect(response.authorization.status).toBe("AUTHORIZATION_UNAVAILABLE");
      expect(response.reason_codes).toContain("AUTHORIZATION_EVALUATOR_INPUT_MISSING");
    }
  });

  it("rejects executable, shell, URL, and environment injection fields", () => {
    for (const field of ["shell", "argv", "executable", "script", "url", "env", "working_directory"]) {
      const response = planOperatorDryRun({
        ...buildDryRunRequest("inspect-project", { project_id: "demo-project" }),
        parameters: { project_id: "demo-project", [field]: "blocked" },
      });
      expect(response.status).toBe("INVALID");
      expect(response.reason_codes).toContain("UNKNOWN_PARAMETER_FIELD");
    }
  });
});

describe("OperatorDryRunPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (_url, init) => ({
      json: async () => planOperatorDryRun(JSON.parse(String((init as RequestInit).body))),
    })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders truthful dry-run labels and no live execution control", () => {
    render(<OperatorDryRunPanel />);

    expect(screen.getByRole("button", { name: "Preview dry run" })).toBeInTheDocument();
    expect(screen.getByText(/never executes, renders, dispatches/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Run$/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Render now")).not.toBeInTheDocument();
    expect(screen.getByText("No side effects performed")).toBeInTheDocument();
  });

  it("supports keyboard operation selection and READY preview submission", async () => {
    render(<OperatorDryRunPanel />);

    fireEvent.change(screen.getByLabelText("Dry run operation"), { target: { value: "inspect-project" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview dry run" }));

    await waitFor(() => expect(screen.getByText("READY")).toBeInTheDocument());
    expect(screen.getByText(/READ_ONLY_PROJECT_LOOKUP_PREVIEW → demo-project/)).toBeInTheDocument();
  });

  it("invalid inputs prevent submission", () => {
    const fetchSpy = vi.mocked(fetch);
    render(<OperatorDryRunPanel />);

    fireEvent.change(screen.getByLabelText("Project id"), { target: { value: "bad/project" } });
    expect(screen.getByRole("button", { name: "Preview dry run" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Preview dry run" }));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("PROJECT_ID_UNSAFE");
  });

  it("loading prevents duplicate submission", async () => {
    let release!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { release = resolve; })));
    render(<OperatorDryRunPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Preview dry run" }));
    expect(screen.getByRole("button", { name: "Preview pending..." })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Preview pending..." }));
    expect(fetch).toHaveBeenCalledTimes(1);
    release({ json: async () => planOperatorDryRun(buildDryRunRequest("inspect-project", { project_id: "demo-project" })) });
    await waitFor(() => expect(screen.getByRole("button", { name: "Preview dry run" })).toBeInTheDocument());
  });

  it("renders authorization UNAVAILABLE truthfully without fake success", async () => {
    render(<OperatorDryRunPanel />);

    fireEvent.change(screen.getByLabelText("Dry run operation"), { target: { value: "initialize-project" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview dry run" }));
    await waitFor(() => expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument());
    expect(screen.getByText("AUTHORIZATION_UNAVAILABLE")).toBeInTheDocument();

    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    fireEvent.click(screen.getByRole("button", { name: "Preview dry run" }));
    await waitFor(() => expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
  });

  it("shows prerequisites, proposed actions, prohibited actions, warnings, and reason codes", () => {
    render(<OperatorDryRunPanel />);

    expect(screen.getByText("Prerequisites")).toBeInTheDocument();
    expect(screen.getByText("Proposed actions (preview order)")).toBeInTheDocument();
    expect(screen.getByText("Prohibited actions")).toBeInTheDocument();
    expect(screen.getByText("Reason codes")).toBeInTheDocument();
    expect(screen.getByText(/invoke_hvs/)).toBeInTheDocument();
    expect(screen.getByText("SIDE_EFFECTS_ZERO")).toBeInTheDocument();
  });

  it("does not use clipboard or browser storage", () => {
    const localStorageGet = vi.spyOn(Storage.prototype, "getItem");
    const localStorageSet = vi.spyOn(Storage.prototype, "setItem");
    const clipboardWrite = vi.fn();
    Object.assign(navigator, { clipboard: { writeText: clipboardWrite } });

    render(<OperatorDryRunPanel />);

    expect(localStorageGet).not.toHaveBeenCalled();
    expect(localStorageSet).not.toHaveBeenCalled();
    expect(clipboardWrite).not.toHaveBeenCalled();
  });

  it("keeps Cohort 9A app shell route functional while adding the dry-run surface", () => {
    render(<AppShell />);

    expect(screen.getAllByText("Operator Dry Run").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Operator Read Surface").length).toBeGreaterThan(0);
  });
});
