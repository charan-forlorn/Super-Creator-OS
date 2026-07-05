// SCOS Control Center - Stage 5.5 Operator Packet Review types.
// Static frontend mirror only. No backend calls, persistence, dispatch, or
// clipboard behavior is implemented here.

import type {
  PacketAgentName,
  PacketResultType,
  PacketVerdict,
  PromptPacketType,
  RoutingPriority,
} from "./prompt-result-packet-types";

export type PacketReviewCheckStatus = "success" | "failure" | "skipped";
export type PacketReviewCheckSeverity = "info" | "warning" | "error" | "critical";

export type OperatorPacketDecision =
  | "approve"
  | "reject"
  | "request_changes"
  | "manual_handoff"
  | "blocked";

export type ReviewQueueStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "changes_requested"
  | "manual_handoff_prepared"
  | "blocked";

export type HandoffMode =
  | "manual_clipboard"
  | "manual_app"
  | "manual_cli"
  | "manual_review_only";

export interface PacketReviewCheckView {
  checkName: string;
  status: PacketReviewCheckStatus;
  severity: PacketReviewCheckSeverity;
  errorDetail: string | null;
}

export interface ManualHandoffPreviewView {
  handoffId: string;
  targetAgent: PacketAgentName;
  targetRuntimeId: string;
  handoffMode: HandoffMode;
  promptPreview: string;
  contextSummaryPreview: string;
  steps: readonly string[];
  manifestPath: string;
}

export interface OperatorPacketReviewView {
  reviewId: string;
  packetId: string;
  resultPacketId: string | null;
  packetType: PromptPacketType | PacketResultType;
  sourceAgent: PacketAgentName;
  targetAgent: PacketAgentName;
  targetRuntimeId: string;
  routingDecisionId: string | null;
  routingReason: string;
  routingPriority: RoutingPriority;
  verdict: PacketVerdict | null;
  title: string;
  objective: string;
  requiredDecision: OperatorPacketDecision;
  status: ReviewQueueStatus;
  checks: readonly PacketReviewCheckView[];
  handoffPreview: ManualHandoffPreviewView | null;
  operatorNote: string;
}
