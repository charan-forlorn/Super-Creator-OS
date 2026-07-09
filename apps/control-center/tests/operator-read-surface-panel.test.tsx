import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { OperatorReadSurfacePanel } from "@/components/operator-read-surface-panel";
import { AppShell } from "@/components/app-shell";
import {
  emptyOperatorReadSurfaceProjection,
  errorOperatorReadSurfaceProjection,
  loadingOperatorReadSurfaceProjection,
  populatedOperatorReadSurfaceProjection,
} from "@/lib/operator-read-surface-mock-data";

describe("OperatorReadSurfacePanel", () => {
  it("renders populated readiness, health signals, activity, and coherence", () => {
    render(<OperatorReadSurfacePanel projection={populatedOperatorReadSurfaceProjection} />);

    expect(screen.getByText("Operator Readiness Summary")).toBeInTheDocument();
    expect(screen.getByText("BACKEND")).toBeInTheDocument();
    expect(screen.getByText("HOST METRICS")).toBeInTheDocument();
    expect(screen.getByText("Recent Activity")).toBeInTheDocument();
    expect(screen.getByText("Read Surface Coherence")).toBeInTheDocument();
  });

  it("renders loading state without crashing", () => {
    render(<OperatorReadSurfacePanel projection={loadingOperatorReadSurfaceProjection} />);

    expect(
      screen.getByText("Loading deterministic operator projection fixture."),
    ).toBeInTheDocument();
  });

  it("renders empty fallback guidance", () => {
    render(<OperatorReadSurfacePanel projection={emptyOperatorReadSurfaceProjection} />);

    expect(
      screen.getByText(/No approved local operator projection is available/i),
    ).toBeInTheDocument();
  });

  it("renders error blockers without presenting the coherence state as healthy", () => {
    render(<OperatorReadSurfacePanel projection={errorOperatorReadSurfaceProjection} />);

    expect(screen.getAllByText("error").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Coherence blocker visible in error fixture.").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("healthy", { selector: "span" })).toHaveLength(0);
  });

  it("keeps the static fallback notice visible", () => {
    render(<OperatorReadSurfacePanel projection={populatedOperatorReadSurfaceProjection} />);

    expect(
      screen.getAllByText(
        "Stage 7.4 uses deterministic local projection data. Live transport is deferred to Stage 7.5 decision.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("keeps the existing app shell render path intact", () => {
    render(<AppShell />);

    expect(screen.getAllByText("Operator Read Surface").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Task Board").length).toBeGreaterThan(0);
  });
});
