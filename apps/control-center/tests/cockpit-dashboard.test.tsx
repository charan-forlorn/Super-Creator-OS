import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

describe("Agent Operations Cockpit", () => {
  it("renders the requested deterministic operational map in Thai by default", () => {
    render(<CockpitDashboard />);

    expect(screen.getByText("ตรวจทานและอนุมัติหลักฐาน Stage 8S")).toBeInTheDocument();
    expect(screen.getByText("Hermes Desktop")).toBeInTheDocument();
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Codex")).toBeInTheDocument();
    expect(screen.getByText("HVS")).toBeInTheDocument();
    expect(screen.getByText("n8n")).toBeInTheDocument();
    expect(screen.getAllByText("25 tests passed").length).toBeGreaterThan(0);
  });

  it("switches all cockpit UI copy to English without persisting locale", () => {
    window.localStorage.clear();
    render(<CockpitDashboard />);

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByText("Review & Approve Stage 8S Evidence")).toBeInTheDocument();
    expect(screen.getByText("Agent workflow")).toBeInTheDocument();
    expect(window.localStorage.getItem("scos-cockpit-locale")).toBeNull();
  });

  it("shows deterministic local-only feedback for evidence review", () => {
    render(<CockpitDashboard />);

    fireEvent.click(screen.getByRole("button", { name: "ตรวจทานหลักฐาน" }));

    expect(screen.getByRole("status")).toHaveTextContent("ไม่มีการเปลี่ยนแปลงสถานะภายนอก");
  });

  it("renders mascot as the static CSS-native Orbit (no canvas, no runtime image)", () => {
    const { container } = render(<CockpitDashboard />);
    const briefing = container.querySelector(".orbit-briefing");

    expect(briefing).toBeInTheDocument();
    // CSS-native orbit is rendered; no canvas element is used.
    expect(briefing?.querySelector("canvas")).toBeNull();
    expect(briefing?.querySelector(".cockpit-orbit")).toBeInTheDocument();
  });
});
