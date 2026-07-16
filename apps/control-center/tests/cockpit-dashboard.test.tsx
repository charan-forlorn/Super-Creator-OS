import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import Page from "@/app/page";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

describe("Agent Operations Cockpit — truthful read-only bridge", () => {
  it("defaults to live local read-only mode with a visible source badge", () => {
    render(<CockpitDashboard />);
    // Live badge must be present by default (never demo by default).
    expect(screen.getByText(/Live local read-only/i)).toBeInTheDocument();
    // Demo label must NOT be shown in live mode.
    expect(screen.queryByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).not.toBeInTheDocument();
  });

  it("shows a loading state or resolved live data, never mock operational truth", () => {
    render(<CockpitDashboard />);
    const loading = screen.queryByText(/Reading local SCOS state/i);
    const liveData = screen.queryByText(/Live local read-only/i);
    // Either the loading text or resolved live data is acceptable; the key
    // contract is that the cockpit must never present mock/demo operational
    // state as real system truth.
    expect(loading !== null || liveData !== null).toBe(true);
    expect(screen.queryByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).not.toBeInTheDocument();
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
    const dryRunPanel = screen.getByRole("region", { name: "Operator dry-run preview" });
    expect(within(dryRunPanel).getByRole("heading", { name: "Operator dry-run preview" })).toBeInTheDocument();
    expect(within(dryRunPanel).getByRole("button", { name: "Preview dry run" })).toBeInTheDocument();
    expect(within(dryRunPanel).getByText("side_effects_performed = false")).toBeInTheDocument();
  });

  it("exposes the Cohort 10A workflow exactly once on the actual product route", () => {
    render(<Page />);

    expect(screen.getByText("SCOS")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Video-production request" })).toHaveLength(1);
    expect(screen.getByText("Cohort 10A control loop")).toBeInTheDocument();
  });

  it("exposes the Cohort 10B project-preparation workflow exactly once without replacing Cohort 10A", () => {
    render(<Page />);

    expect(screen.getAllByRole("heading", { name: "Project draft and render-preparation preview" })).toHaveLength(1);
    expect(screen.getByText("Cohort 10B planning surface")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Video-production request" })).toHaveLength(1);
    expect(screen.queryByText(/Project initialized|Render started|Published|Uploaded/i)).not.toBeInTheDocument();
  });

  it("renders Orbit as the static CSS-native mascot (no canvas, no runtime image)", () => {
    const { container } = render(<CockpitDashboard />);
    const briefing = container.querySelector(".orbit-briefing");
    expect(briefing).toBeInTheDocument();
    expect(briefing?.querySelector("canvas")).toBeNull();
    expect(briefing?.querySelector(".cockpit-orbit")).toBeInTheDocument();
  });
});
