import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";
import { ApprovalsScreen, EvidenceScreen, ProjectsScreen } from "@/components/cockpit/cockpit-routes";

describe("Cockpit V0.2 routes", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("wires Today, Projects, Approvals, and Evidence to their App Router paths", () => {
    render(<CockpitDashboard />);

    expect(screen.getByRole("link", { name: "1 วันนี้" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "2 โปรเจกต์" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "5 หลักฐาน" })).toHaveAttribute("href", "/evidence");
    expect(screen.getByRole("link", { name: "6 การอนุมัติ" })).toHaveAttribute("href", "/approvals");
  });

  it("renders V0.2 project fixtures and updates the selected detail locally", () => {
    render(<ProjectsScreen />);

    expect(screen.getAllByText("การเชื่อมต่อ SCOS–HVS").length).toBeGreaterThan(0);
    expect(screen.getByText("โรงงานเวิร์กโฟลว์ Hermes")).toBeInTheDocument();
    expect(screen.getByText("โครงการนำร่องวิดีโอลูกค้า")).toBeInTheDocument();

    fireEvent.click(screen.getByText("โรงงานเวิร์กโฟลว์ Hermes"));

    expect(screen.getByRole("status")).toHaveTextContent("อัปเดตรายละเอียดโปรเจกต์บนเครื่องแล้ว");
    expect(screen.getByText("ติดตามรอบตรวจทานเวิร์กโฟลว์บนเครื่องถัดไป")).toBeInTheDocument();
  });

  it("switches a new route to English through the shared locale provider", () => {
    render(<ProjectsScreen />);

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getAllByText("SCOS–HVS Integration").length).toBeGreaterThan(0);
  });

  it("updates approval state and activity only in local UI state", () => {
    render(<ApprovalsScreen />);

    fireEvent.click(screen.getAllByRole("button", { name: "อนุมัติ" })[0]);

    expect(screen.getAllByText("อนุมัติแล้ว").length).toBeGreaterThan(0);
    expect(screen.getByText("บันทึกการตัดสินใจ Stage 8S บนเครื่องแล้ว")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("ไม่มีการเรียกใช้บริการภายนอก");
  });

  it("opens a deterministic evidence detail panel", () => {
    render(<EvidenceScreen />);
    const commitRecord = screen.getByText("คอมมิต 00aafbb").closest("article");

    expect(commitRecord).not.toBeNull();
    fireEvent.click(within(commitRecord!).getByRole("button", { name: "เปิดหลักฐาน" }));

    expect(screen.getByRole("complementary", { name: "คอมมิต 00aafbb" })).toBeInTheDocument();
    expect(screen.getByText("00aafbb")).toBeInTheDocument();
  });

  it("keeps the technical value visible without copying or showing a copied state", () => {
    render(<EvidenceScreen />);
    const commitRecord = screen.getByText("คอมมิต 00aafbb").closest("article");
    fireEvent.click(within(commitRecord!).getByRole("button", { name: "เปิดหลักฐาน" }));

    const panel = screen.getByRole("complementary", { name: "คอมมิต 00aafbb" });
    // Technical value is shown in the detail list.
    expect(within(panel).getByText("00aafbb")).toBeInTheDocument();
    // No copy button is rendered; no false "Copied" feedback appears.
    expect(within(panel).queryByRole("button", { name: /คัดลอก|copy/i })).toBeNull();
    expect(screen.queryByText(/คัดลอกค่าทางเทคนิคบนเครื่องแล้ว|copied/i)).not.toBeInTheDocument();
  });

  it("exposes Agents, Workflows, Activity, and Settings as unavailable controls that cannot activate", () => {
    const { container } = render(<CockpitDashboard />);
    const unavailable = Array.from(
      container.querySelectorAll<HTMLButtonElement>("nav.cockpit-nav button.cockpit-nav__item.is-unavailable"),
    );
    expect(unavailable.length).toBe(4);

    for (const item of unavailable) {
      expect(item).toBeDisabled();
      expect(item).toHaveAttribute("aria-disabled", "true");
      // Activation must not throw or change document state.
      expect(() => fireEvent.click(item)).not.toThrow();
    }

    // No new route is navigated to and no console error path is taken.
    expect(window.location.pathname).toBe("/");
  });
});
