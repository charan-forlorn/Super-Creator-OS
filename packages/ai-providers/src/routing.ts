import {
  evaluateCapabilityCandidate,
  type CapabilityAdmission,
  type CapabilityCandidate,
  type CapabilityName,
  type CostClass,
  type CurrentnessState,
  type HealthState,
  type QualificationState,
  type LicenceState,
  type HardwareFit,
} from "./capabilities.js";

export interface RouteCandidate extends CapabilityCandidate {
  providerId: string;
  modelId: string;
}

export type RouteRejectionReason = CapabilityAdmission extends infer A
  ? A extends { eligible: false; reason: infer R } ? R : never
  : never;

export function evaluateRouteCandidate(candidate: RouteCandidate): CapabilityAdmission {
  return evaluateCapabilityCandidate(candidate);
}
