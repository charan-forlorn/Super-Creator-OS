export type Locale = "th" | "en";

export type AgentStatus = "completed" | "in-progress" | "waiting" | "blocked";
export type OrbitState = "normal" | "attention" | "success";

export type ProjectId = "scos-core" | "orbit-lab";

export interface CockpitProject {
  id: ProjectId;
  stage: string;
  state: "certified" | "awaiting-review";
}

export interface CockpitAgent {
  id: "hermes" | "claude" | "codex" | "hvs" | "n8n";
  status: AgentStatus;
  progress: number;
}

export interface CockpitTask {
  id: "review-stage-8s" | "video-review" | "scheduled-run";
  status: AgentStatus;
}

export interface ApprovalItem {
  id: "stage-8s";
  stage: string;
  evidenceIds: string[];
}

export interface EvidenceItem {
  id: "tests" | "commit" | "hvs-render" | "n8n-run";
  value: string;
}

export interface ActivityEntry {
  id: "certification" | "build" | "review";
  tone: "success" | "info" | "warning";
}

export interface OrbitBriefing {
  state: OrbitState;
}

export type ProjectV02Id = "scos-hvs" | "hermes-factory" | "client-video";
export type ProjectFilter = "all" | "active" | "needs-you" | "completed";
export type ProjectV02Status = "active" | "healthy" | "needs-you" | "completed";
export type ApprovalId = "stage-8s" | "asset-rights" | "weekly-schedule";
export type ApprovalPriority = "high" | "medium" | "low";
export type ApprovalDecision = "pending" | "approved" | "changes-requested" | "rejected";
export type EvidenceV02Id = "stage-8r" | "stage-8s-tests" | "commit-00aafbb" | "hvs-render" | "n8n-schedule";
export type EvidenceStatus = "verified" | "passed" | "healthy";
export type EvidenceSource = "hermes" | "codex" | "git" | "hvs" | "n8n";

export interface ProjectV02 {
  id: ProjectV02Id;
  status: ProjectV02Status;
  stage: string;
  lead: CockpitAgent["id"];
  lastActivity: string;
  evidenceValue: string;
  hasRisk: boolean;
}

export interface ApprovalQueueItem {
  id: ApprovalId;
  priority: ApprovalPriority;
  requestedBy: EvidenceSource;
  deadline: string;
  risk: "low" | "medium" | "high";
  relatedEvidenceId: EvidenceV02Id;
}

export interface EvidenceRecord {
  id: EvidenceV02Id;
  projectId: ProjectV02Id;
  stage: string;
  source: EvidenceSource;
  status: EvidenceStatus;
  timestamp: string;
  technicalValue?: string;
}
