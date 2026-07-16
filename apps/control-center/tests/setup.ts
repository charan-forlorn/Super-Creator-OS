// Stage 6.7 test setup. Registers the jest-dom custom matchers
// (toBeInTheDocument, toHaveTextContent, ...) for every test file.
import "@testing-library/jest-dom";
import { vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

// jsdom does not implement the 2D canvas API. Orbit uses Canvas only in the
// browser, so tests receive a narrow deterministic drawing surface instead.
const canvasContext = {
  setTransform: vi.fn(),
  clearRect: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  rotate: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  clip: vi.fn(),
  drawImage: vi.fn(),
  ellipse: vi.fn(),
  fill: vi.fn(),
  fillStyle: "",
};

// jsdom does not implement fetch. Provide a default read-only transport stub
// so components using useControlCenterData render without crashing. Individual
// tests may override global.fetch with vi.stubGlobal.
const defaultSnapshot = {
  schema_version: 1,
  snapshot_id: "ccs-default",
  generated_at: "2026-07-16T00:00:00Z",
  source_mode: "LIVE_LOCAL_READ_ONLY",
  health: { available: true, status: "AVAILABLE_WITH_DATA", data: { health_status: "healthy", artifact_count: 1, event_count: 0, command_record_count: 0, audit_record_count: 0, warning_count: 0, blocker_count: 0, source_coverage: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
  queue_summary: { available: true, status: "AVAILABLE_EMPTY", data: { count: 0, items: [] }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" },
  approval_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T00:00:00Z" },
  project_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { state_tables_present: ["projects"], has_dedicated_project_model: false }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
  evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T00:00:00Z" },
  recent_activity: { available: true, status: "AVAILABLE_WITH_DATA", data: { count: 0, items: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
  degradation_reasons: ["READ_SOURCE_MISSING"],
};

if (typeof globalThis.fetch === "undefined") {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => defaultSnapshot,
  }) as unknown as typeof fetch;
}
