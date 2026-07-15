import type {
  ActivityEntry,
  ApprovalItem,
  CockpitAgent,
  CockpitProject,
  CockpitTask,
  EvidenceItem,
  EvidenceRecord,
  OrbitBriefing,
  ApprovalQueueItem,
  ProjectV02,
} from "@/lib/cockpit-types";

export const COCKPIT_PROJECTS: readonly CockpitProject[] = [
  { id: "scos-core", stage: "Stage 8S", state: "awaiting-review" },
  { id: "orbit-lab", stage: "Stage 8R", state: "certified" },
];

export const COCKPIT_AGENTS: readonly CockpitAgent[] = [
  { id: "hermes", status: "completed", progress: 100 },
  { id: "claude", status: "completed", progress: 100 },
  { id: "codex", status: "waiting", progress: 92 },
  { id: "hvs", status: "in-progress", progress: 68 },
  { id: "n8n", status: "waiting", progress: 0 },
];

export const COCKPIT_TASKS: readonly CockpitTask[] = [
  { id: "review-stage-8s", status: "waiting" },
  { id: "video-review", status: "in-progress" },
  { id: "scheduled-run", status: "waiting" },
];

export const COCKPIT_APPROVAL: ApprovalItem = {
  id: "stage-8s",
  stage: "Stage 8S",
  evidenceIds: ["tests", "commit", "hvs-render"],
};

export const COCKPIT_EVIDENCE: readonly EvidenceItem[] = [
  { id: "tests", value: "25 tests passed" },
  { id: "commit", value: "00aafbb" },
  { id: "hvs-render", value: "All checks passed" },
  { id: "n8n-run", value: "15 July 2026 · 16:00" },
];

export const COCKPIT_ACTIVITY: readonly ActivityEntry[] = [
  { id: "certification", tone: "success" },
  { id: "build", tone: "info" },
  { id: "review", tone: "warning" },
];

export const ORBIT_BRIEFING: OrbitBriefing = { state: "attention" };

export const V02_PROJECTS: readonly ProjectV02[] = [
  { id: "scos-hvs", status: "needs-you", stage: "Stage 8S", lead: "codex", lastActivity: "15 July 2026 · 14:20", evidenceValue: "25 tests passed", hasRisk: false },
  { id: "hermes-factory", status: "healthy", stage: "Operational", lead: "hermes", lastActivity: "15 July 2026 · 13:10", evidenceValue: "Workflow health: healthy", hasRisk: false },
  { id: "client-video", status: "needs-you", stage: "Render Readiness", lead: "hvs", lastActivity: "15 July 2026 · 11:45", evidenceValue: "2 assets awaiting approval", hasRisk: true },
];

export const V02_APPROVALS: readonly ApprovalQueueItem[] = [
  { id: "stage-8s", priority: "high", requestedBy: "codex", deadline: "15 July 2026 · 17:00", risk: "medium", relatedEvidenceId: "stage-8s-tests" },
  { id: "asset-rights", priority: "medium", requestedBy: "hvs", deadline: "16 July 2026 · 10:00", risk: "high", relatedEvidenceId: "hvs-render" },
  { id: "weekly-schedule", priority: "low", requestedBy: "n8n", deadline: "18 July 2026 · 09:00", risk: "low", relatedEvidenceId: "n8n-schedule" },
];

export const V02_EVIDENCE: readonly EvidenceRecord[] = [
  { id: "stage-8r", projectId: "scos-hvs", stage: "Stage 8R", source: "hermes", status: "verified", timestamp: "15 July 2026 · 12:40" },
  { id: "stage-8s-tests", projectId: "scos-hvs", stage: "Stage 8S", source: "codex", status: "passed", timestamp: "15 July 2026 · 14:12", technicalValue: "25 tests passed" },
  { id: "commit-00aafbb", projectId: "scos-hvs", stage: "Stage 8S", source: "git", status: "verified", timestamp: "15 July 2026 · 14:14", technicalValue: "00aafbb" },
  { id: "hvs-render", projectId: "client-video", stage: "Render Readiness", source: "hvs", status: "passed", timestamp: "15 July 2026 · 11:45", technicalValue: "All checks passed" },
  { id: "n8n-schedule", projectId: "hermes-factory", stage: "Operational", source: "n8n", status: "healthy", timestamp: "15 July 2026 · 09:00" },
];
