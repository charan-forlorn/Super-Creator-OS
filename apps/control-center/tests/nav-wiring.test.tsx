import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar, TopNav, NAV_SECTIONS } from "@/components/sidebar";

// Stage 6.7 — navigation wiring test (guards the Stage 5.6 wiring-gap precedent).
// Pure render-level assertions; no component rewrite, no backend imports.
describe("navigation wiring", () => {
  it("renders every NAV_SECTIONS entry in the vertical sidebar", () => {
    render(<Sidebar activeSection="overview" onSelect={() => {}} />);
    for (const section of NAV_SECTIONS) {
      expect(screen.getByText(section.label)).toBeInTheDocument();
    }
  });

  it("renders every NAV_SECTIONS entry in the compact top nav", () => {
    render(<TopNav activeSection="overview" onSelect={() => {}} />);
    for (const section of NAV_SECTIONS) {
      expect(screen.getByText(section.label)).toBeInTheDocument();
    }
  });

  it("marks the active section button with aria-current in TopNav", () => {
    render(<TopNav activeSection="command-bridge" onSelect={() => {}} />);
    const active = screen.getByRole("button", { current: true });
    expect(active).toHaveTextContent("Command Bridge");
  });

  it("wires the global NAV_SECTIONS contract: 22 sections, deterministic order", () => {
    // The app-shell renders one section per NAV_SECTIONS id; assert the
    // contract shape the UI is built against (no drift / missing section).
    expect(NAV_SECTIONS.length).toBe(22);
    expect(NAV_SECTIONS.map((s) => s.id)).toEqual([
      "overview",
      "live",
      "command-bridge",
      "ai-work-sessions",
      "agent-adapters",
      "prompt-packets",
      "packet-review",
      "workflow-router",
      "result-intake",
      "git-approval",
      "operator-execution",
      "stage5-certification",
      "local-backend",
      "durable-state",
      "event-stream",
      "operator-read-surface",
      "operator-dry-run",
      "board",
      "prompt",
      "inbox",
      "merge",
      "timeline",
    ]);
  });
});
