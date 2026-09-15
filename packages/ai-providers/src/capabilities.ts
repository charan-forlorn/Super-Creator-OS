import { z } from "zod";

export const CAPABILITY_NAMES = [
  "generate_text",
  "generate_image",
  "edit_image",
  "generate_video",
  "image_to_video",
  "generate_voice",
  "generate_music",
  "transcribe",
  "remove_background",
  "upscale",
  "analyze_media",
  "edit_video",
  "compose_video",
  "render_video",
] as const;
export type CapabilityName = (typeof CAPABILITY_NAMES)[number];

export const CAPABILITY_AVAILABILITIES = [
  "READY", "PARTIAL", "ADAPTER_ONLY", "EXTERNAL", "LOCAL_NO_MODEL", "PLANNED", "BLOCKED", "UNKNOWN",
] as const;
export type CapabilityAvailability = (typeof CAPABILITY_AVAILABILITIES)[number];

export const COST_CLASSES = [
  "local_zero_inference_cost", "free_keyless", "free_or_variable", "paid", "unknown",
] as const;
export type CostClass = (typeof COST_CLASSES)[number];

export const capabilityDescriptorSchema = z.object({
  capability: z.enum(CAPABILITY_NAMES),
  provider: z.object({ id: z.string().min(1), kind: z.enum(["local", "cloud", "embedded"]) }),
  model: z.object({ id: z.string().min(1), version: z.string().min(1) }).nullable().optional(),
  costClass: z.enum(COST_CLASSES),
  availability: z.enum(CAPABILITY_AVAILABILITIES),
});
export type CapabilityDescriptor = z.infer<typeof capabilityDescriptorSchema>;

export interface ProviderIdentity {
  readonly id: string;
  readonly kind: "local" | "cloud" | "embedded";
}

export type CurrentnessState = "CURRENT" | "STALE" | "INVALID" | "UNKNOWN";
export type HealthState = "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN";
export type QualificationState = "QUALIFIED" | "UNQUALIFIED" | "UNKNOWN";
export type LicenceState = "ALLOWED" | "DENIED" | "UNKNOWN";
export type HardwareFit = "FIT" | "MISS" | "UNKNOWN";

export interface CapabilityCandidate {
  capability: CapabilityName;
  costClass: CostClass;
  availability: CapabilityAvailability;
  currentness: CurrentnessState;
  health: HealthState;
  qualification: QualificationState;
  licence: LicenceState;
  hardware: HardwareFit;
  evidenceComplete: boolean;
}

export const CAPABILITY_REJECTION_REASONS = [
  "capability_unavailable", "unknown_cost", "disallowed_cost", "stale_currentness",
  "invalid_currentness", "unknown_currentness", "unhealthy", "unknown_health",
  "unqualified", "unknown_qualification", "licence_denied", "unknown_licence",
  "hardware_mismatch", "unknown_hardware", "missing_evidence",
] as const;
export type CapabilityRejectionReason = (typeof CAPABILITY_REJECTION_REASONS)[number];
export type CapabilityAdmission = { eligible: true } | { eligible: false; reason: CapabilityRejectionReason };

export function evaluateCapabilityCandidate(candidate: CapabilityCandidate): CapabilityAdmission {
  if (candidate.availability !== "READY") return { eligible: false, reason: "capability_unavailable" };
  if (candidate.costClass === "unknown") return { eligible: false, reason: "unknown_cost" };
  if (candidate.costClass === "paid" || candidate.costClass === "free_or_variable") {
    return { eligible: false, reason: "disallowed_cost" };
  }
  if (candidate.currentness !== "CURRENT") {
    return { eligible: false, reason: candidate.currentness === "STALE" ? "stale_currentness" : candidate.currentness === "INVALID" ? "invalid_currentness" : "unknown_currentness" };
  }
  if (candidate.health !== "HEALTHY") {
    return { eligible: false, reason: candidate.health === "UNKNOWN" ? "unknown_health" : "unhealthy" };
  }
  if (candidate.qualification !== "QUALIFIED") {
    return { eligible: false, reason: candidate.qualification === "UNKNOWN" ? "unknown_qualification" : "unqualified" };
  }
  if (candidate.licence !== "ALLOWED") {
    return { eligible: false, reason: candidate.licence === "UNKNOWN" ? "unknown_licence" : "licence_denied" };
  }
  if (candidate.hardware !== "FIT") {
    return { eligible: false, reason: candidate.hardware === "UNKNOWN" ? "unknown_hardware" : "hardware_mismatch" };
  }
  if (!candidate.evidenceComplete) return { eligible: false, reason: "missing_evidence" };
  return { eligible: true };
}
