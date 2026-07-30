import { act } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { BriefStudio } from "@/components/brief-studio/brief-studio";
import * as client from "@/lib/paid-pilot-intake-client";
import type { BriefProjection, BriefSection, GuidedIntakeDraft, IntakeStatus } from "@/lib/paid-pilot-intake-types";

// Cohort 10K — Brief Studio frontend acceptance. Synthetic data only.

const SECTION_IDS = ["goal", "audience", "message", "style", "channel", "assets", "schedule", "rights"] as const;

function section(id: string, over: Partial<BriefSection> = {}): BriefSection {
  return {
    id,
    heading: id,
    state: "READY",
    blocking: false,
    why_it_matters: "เหตุผลที่ต้องมี",
    how_to_resolve: "วิธีแก้",
    detail: "",
    recommended: [],
    ...over,
  };
}

function projection(over: Partial<BriefProjection> = {}): BriefProjection {
  const sections = SECTION_IDS.map((id) => section(id));
  return {
    schema_version: "brief.v1",
    sections,
    ready_count: 8,
    total_count: 8,
    readiness_label: "พร้อมแล้ว 8 จาก 8 ส่วน",
    overall: "READY",
    answers: { goal: "วิดีโอโปรโมตสินค้า", audience: "ลูกค้าประจำ", main_point: "สูตรใหม่", style_tone: "ทันสมัย", channel: "YouTube", deadline: "2026-08-15" },
    raw_answers: {},
    recommendations: [],
    assets: { available: 1, needs_review: 0, unsupported: 0, missing: 0, names: ["synthetic.png"] },
    resolved_output: { selected_template: "Landscape Product Promo", target_platform: "YouTube / Website", output_profile: "landscape_16_9", duration: "45s" },
    will_not_do: ["ระบบจะไม่เผยแพร่หรืออัปโหลดงานให้อัตโนมัติ"],
    ...over,
  };
}

function draft(status: IntakeStatus = "NEEDS_INPUT", brief: BriefProjection = projection(), over: Partial<GuidedIntakeDraft> = {}): GuidedIntakeDraft {
  return {
    schema_version: "v",
    draft_id: "draft-1",
    status,
    safe_project_title: "Synthetic Brief",
    selected_template: "Landscape Product Promo",
    target_platform: "YouTube / Website",
    output_profile: "landscape_16_9",
    duration: "45s",
    deadline: "2026-08-15",
    commercial_reference: "brief-studio",
    asset_references: [],
    consent_state: "CONSENT_CONFIRMED",
    consent_evidence_reference: "redacted.txt",
    consent_evidence_sha256: "a".repeat(64),
    explicit_consent_confirmed: true,
    rights_answers: {},
    privacy_answers: {},
    derived_classification: "STANDARD_COMMERCIAL",
    retention_policy: "30 days",
    external_action_restrictions: { upload: "NOT_AUTHORIZED" },
    validation_findings: [],
    generated: { brief },
    created_at: "t",
    updated_at: "t",
    revision: 1,
    pilot_safe_id: "pilot-1",
    project_safe_id: "project-1",
    admission_packet_sha256: "",
    brief_mode: true,
    brief_answers: {},
    ...over,
  };
}

const ok = (d: GuidedIntakeDraft) => ({ ok: true, error_code: null, detail: null, draft: d });

async function click(name: RegExp) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
}

describe("BriefStudio", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/brief-studio");
  });

  it("opens on the first plain-language step with no technical input surface", () => {
    render(<BriefStudio />);
    expect(screen.getByRole("heading", { name: /คุณอยากสร้างอะไร/ })).toBeTruthy();
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/YAML|JSON|schema_version|localStorage|C:\\/);
    expect(body).not.toMatch(/vertical_9_16|landscape_16_9|codec|frame rate/i);
    expect(screen.queryByRole("textbox", { name: /JSON|YAML/i })).toBeNull();
    // plain Thai labels, no internal template id exposed
    expect(screen.getByRole("radio", { name: "วิดีโอโปรโมตสินค้า" })).toBeTruthy();
    expect(body).not.toMatch(/Vertical Product Promo/);
  });

  it("keeps advanced technical details collapsed until explicitly opened", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft()));
    render(<BriefStudio initialDraftId="draft-1" />);
    const toggle = await screen.findByRole("button", { name: /รายละเอียดเพิ่มเติม/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(document.body.textContent).not.toMatch(/landscape_16_9/);
    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("landscape_16_9")).toBeTruthy();
  });

  it("saves a section through the authority, publishes the draft identity and shows a truthful saved state", async () => {
    const create = vi.spyOn(client, "createIntakeDraft").mockResolvedValue(ok(draft()));
    const save = vi.spyOn(client, "saveBriefSection").mockResolvedValue(ok(draft()));
    render(<BriefStudio />);
    await act(async () => {
      fireEvent.click(screen.getByRole("radio", { name: "วิดีโอให้ความรู้" }));
    });
    await click(/ถัดไป/);
    await waitFor(() => expect(screen.getByText("บันทึกแล้ว")).toBeTruthy());
    expect(create).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("draft-1", "goal", expect.objectContaining({ goal: "วิดีโอให้ความรู้" }));
    expect(window.location.search).toContain("draft_id=draft-1");
  });

  it("shows a save failure and never renders it as saved", async () => {
    vi.spyOn(client, "createIntakeDraft").mockResolvedValue(ok(draft()));
    vi.spyOn(client, "saveBriefSection").mockResolvedValue({ ok: false, error_code: "REQUEST_FAILED", detail: null, draft: null });
    render(<BriefStudio />);
    await click(/ถัดไป/);
    await waitFor(() => expect(screen.getByText("บันทึกไม่สำเร็จ")).toBeTruthy());
    expect(screen.queryByText("บันทึกแล้ว")).toBeNull();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/ระบบเบื้องหลังไม่ตอบสนอง/);
    expect(alert.textContent).not.toMatch(/C:\\|Traceback|stderr|SCOS_PYTHON_INTERPRETER/);
    // still on step 1 — no false forward progress
    expect(screen.getByRole("heading", { name: /คุณอยากสร้างอะไร/ })).toBeTruthy();
  });

  it("resumes from the authoritative draft id without touching browser storage", async () => {
    const storageRead = vi.spyOn(Storage.prototype, "getItem");
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    const sessionRead = vi.spyOn(window.sessionStorage, "getItem");
    const sessionWrite = vi.spyOn(window.sessionStorage, "setItem");
    const get = vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("NEEDS_INPUT", projection(), { brief_answers: { goal: "วิดีโอรีวิว" } })));

    render(<BriefStudio initialDraftId="draft-1" />);

    await waitFor(() => expect(screen.getByRole("radio", { name: "วิดีโอรีวิว" }).getAttribute("aria-checked")).toBe("true"));
    expect(get).toHaveBeenCalledWith("draft-1");
    expect(storageRead).not.toHaveBeenCalled();
    expect(storageWrite).not.toHaveBeenCalled();
    expect(sessionRead).not.toHaveBeenCalled();
    expect(sessionWrite).not.toHaveBeenCalled();
  });

  it("surfaces an invalid draft identity safely", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue({ ok: false, error_code: "DRAFT_NOT_FOUND", detail: null, draft: null });
    render(<BriefStudio initialDraftId="missing" />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/ไม่พบบรีฟนี้/));
  });

  it("labels a creative recommendation and keeps the section unblocked", async () => {
    const brief = projection({
      recommendations: [{ field: "style_tone", value: "เรียบง่ายและน่าเชื่อถือ", label: "คำแนะนำของระบบ (ยังเปลี่ยนได้)", reason: "คุณยังไม่แน่ใจ" }],
      sections: SECTION_IDS.map((id) => section(id)),
    });
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("NEEDS_INPUT", brief)));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getAllByText(/คำแนะนำของระบบ/).length).toBeGreaterThan(0));
    const stepper = screen.getByRole("navigation", { name: /ขั้นตอนการทำบรีฟ/ });
    expect(within(stepper).getByRole("button", { name: /สไตล์.*พร้อมแล้ว/ })).toBeTruthy();
  });

  it("blocks creation while a rights answer is uncertain and explains why", async () => {
    const brief = projection({
      overall: "BLOCKED_FOR_RIGHTS",
      ready_count: 7,
      readiness_label: "พร้อมแล้ว 7 จาก 8 ส่วน",
      sections: SECTION_IDS.map((id) =>
        id === "rights" ? section(id, { state: "BLOCKED_FOR_RIGHTS", blocking: true, detail: "ยังมีคำตอบเรื่องสิทธิ์ที่ไม่ชัดเจน" }) : section(id),
      ),
    });
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("NEEDS_INPUT", brief)));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 7 จาก 8 ส่วน")).toBeTruthy());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ยืนยันและสร้าง/ }));
    });
    const confirm = screen.getByRole("button", { name: /ยืนยันบรีฟและสร้างโปรเจกต์/ });
    expect(confirm).toBeDisabled();
    expect(screen.getAllByText(/ยังมีคำตอบเรื่องสิทธิ์ที่ไม่ชัดเจน/).length).toBeGreaterThan(0);
  });

  it("marks a rights Not sure answer as blocking in the question card", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft()));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 8 จาก 8 ส่วน")).toBeTruthy());
    const side = screen.getByRole("complementary", { name: /สรุปบรีฟ/ });
    await act(async () => {
      fireEvent.click(within(side).getByRole("button", { name: /สิทธิ์และความเป็นส่วนตัว/ }));
    });
    const group = screen.getByRole("radiogroup", { name: /ภาพและวิดีโอที่จะใช้ เป็นของใคร/ });
    await act(async () => {
      fireEvent.click(within(group).getByRole("radio", { name: "ยังไม่แน่ใจ" }));
    });
    expect(screen.getAllByRole("alert").some((n) => /ตอบว่ายังไม่แน่ใจไม่ได้/.test(n.textContent ?? ""))).toBe(true);
  });

  it("allows jumping back to any section from the review step", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft()));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 8 จาก 8 ส่วน")).toBeTruthy());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ตรวจทานบรีฟ/ }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ข้อความหลัก · แก้ไข/ }));
    });
    expect(screen.getByRole("heading", { name: /ข้อความหลักคืออะไร/ })).toBeTruthy();
  });

  it("performs exactly one final creation and reports one project identity", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("READY_TO_CREATE")));
    const create = vi.spyOn(client, "createPilotFromDraft").mockResolvedValue({
      ok: true,
      error_code: null,
      detail: null,
      pilot_safe_id: "pilot-1",
      project_safe_id: "project-1",
      admission_packet_sha256: "c".repeat(64),
      draft: draft("CREATED", projection({ overall: "CREATED" })),
    });
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 8 จาก 8 ส่วน")).toBeTruthy());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ยืนยันและสร้าง/ }));
    });
    await click(/ยืนยันบรีฟและสร้างโปรเจกต์/);
    await waitFor(() => expect(screen.getByRole("heading", { name: /สร้างโปรเจกต์เรียบร้อยแล้ว/ })).toBeTruthy());
    expect(create).toHaveBeenCalledTimes(1);
    expect(screen.getByText("project-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ยืนยันบรีฟและสร้างโปรเจกต์/ })).toBeNull();
  });

  it("maps a conflicting replay to a plain-language message without duplicate creation", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("READY_TO_CREATE")));
    const create = vi.spyOn(client, "createPilotFromDraft").mockResolvedValue({ ok: false, error_code: "CONFLICTING_REPLAY_REJECTED", detail: null, draft: null });
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 8 จาก 8 ส่วน")).toBeTruthy());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ยืนยันและสร้าง/ }));
    });
    await click(/ยืนยันบรีฟและสร้างโปรเจกต์/);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/ถูกสร้างเป็นโปรเจกต์ไปแล้ว/));
    expect(create).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("heading", { name: /สร้างโปรเจกต์เรียบร้อยแล้ว/ })).toBeNull();
  });

  it("reports missing assets truthfully with browser-safe names only", async () => {
    const brief = projection({
      assets: { available: 0, needs_review: 1, unsupported: 0, missing: 1, names: ["clip.mov"] },
      sections: SECTION_IDS.map((id) => (id === "assets" ? section(id, { state: "BLOCKED_FOR_ASSETS", blocking: true, detail: "ไฟล์ที่จำเป็นยังไม่พร้อม" }) : section(id))),
    });
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft("NEEDS_INPUT", brief)));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getAllByText(/ไฟล์ที่จำเป็นยังไม่พร้อม/).length).toBeGreaterThan(0));
    const side = screen.getByRole("complementary", { name: /สรุปบรีฟ/ });
    await act(async () => {
      fireEvent.click(within(side).getByRole("button", { name: /ไฟล์ที่มี/ }));
    });
    expect(screen.getByText("clip.mov")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/C:\\|\/Users\/|input_root/);
  });

  it("exposes accessible step status and native keyboard-reachable controls", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue(ok(draft()));
    render(<BriefStudio initialDraftId="draft-1" />);
    await waitFor(() => expect(screen.getByText("พร้อมแล้ว 8 จาก 8 ส่วน")).toBeTruthy());
    expect(screen.getAllByRole("button").every((b) => b.tagName === "BUTTON")).toBe(true);
    expect(document.querySelector('[aria-current="step"]')).toBeTruthy();
    expect(screen.getAllByRole("radiogroup").length).toBeGreaterThan(0);
    expect(document.querySelectorAll('div[onclick]').length).toBe(0);
  });
});
