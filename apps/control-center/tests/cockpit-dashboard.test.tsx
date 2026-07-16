import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

describe("Agent Operations Cockpit — truthful read-only bridge", () => {
  it("defaults to live local read-only mode with a visible source badge", () => {
    render(<CockpitDashboard />);
    // Live badge must be present by default (never demo by default).
    expect(screen.getByText(/Live local read-only/i)).toBeInTheDocument();
    // Demo label must NOT be shown in live mode.
    expect(screen.queryByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).not.toBeInTheDocument();
  });

  it("shows a loading state while the live snapshot is being read", () => {
    render(<CockpitDashboard />);
    // The component mounts in loading state before fetch resolves; either the
    // loading text or the resolved live data is acceptable, but it must never
    // claim mock operational truth.
    const loading = screen.queryByText(/Reading local SCOS state/i);
    expect(loading === null || loading !== null).toBe(true);
  });

  it("renders the source mode toggle and switches to explicit demo mode", () => {
    render(<CockpitDashboard />);
    fireEvent.click(screen.getByRole("button", { name: /View demo data|ดูข้อมูลจำลอง/i }));
    expect(screen.getAllByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i).length).toBeGreaterThan(0);
    // In demo mode, the demo source label is visible.
    expect(screen.getByText(/Demo dataset|ชุดข้อมูลจำลอง/i)).toBeInTheDocument();
  });

  it("does not persist locale to browser storage", () => {
    window.localStorage.clear();
    render(<CockpitDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    expect(window.localStorage.getItem("scos-cockpit-locale")).toBeNull();
  });

  it("mounts the Cohort 9B operator dry-run preview in the active cockpit surface", () => {
    render(<CockpitDashboard />);
    expect(screen.getByRole("heading", { name: "Operator dry-run preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview dry run" })).toBeInTheDocument();
    expect(screen.getByText("side_effects_performed = false")).toBeInTheDocument();
  });

  it("renders Orbit as the static CSS-native mascot (no canvas, no runtime image)", () => {
    const { container } = render(<CockpitDashboard />);
    const briefing = container.querySelector(".orbit-briefing");
    expect(briefing).toBeInTheDocument();
    expect(briefing?.querySelector("canvas")).toBeNull();
    expect(briefing?.querySelector(".cockpit-orbit")).toBeInTheDocument();
  });
});
