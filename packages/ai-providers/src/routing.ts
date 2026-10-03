import {
  evaluateCapabilityCandidate,
  type CapabilityAdmission,
  type CapabilityName,
  type CapabilityRejectionReason,
  type CostClass,
  type CurrentnessState,
  type HealthState,
  type QualificationState,
  type LicenceState,
  type HardwareFit,
} from "./capabilities.js";

export interface RouteCandidate {
  capability: CapabilityName;
  providerId: string;
  modelId: string;
  modelVersion?: string;
  costClass: CostClass;
  availability: "READY" | "PARTIAL" | "ADAPTER_ONLY" | "EXTERNAL" | "LOCAL_NO_MODEL" | "PLANNED" | "BLOCKED" | "UNKNOWN";
  currentness: CurrentnessState;
  health: HealthState;
  qualification: QualificationState;
  licence: LicenceState;
  hardware: HardwareFit;
  evidenceComplete: boolean;
  priority?: number;
}

export interface GovernanceEvidence {
  currentness: CurrentnessState;
  qualification: QualificationState;
  licence: LicenceState;
  hardware: HardwareFit;
  allowedCostClasses: readonly CostClass[];
  evidenceComplete: boolean;
  evidenceRefs: readonly string[];
}

export interface MachineCapabilityEvidence {
  observedAt: string;
  providerId: string;
  providerReachable: boolean;
  modelId: string;
  modelVersion?: string;
  modelPresent: boolean;
  health: HealthState;
  evidenceRefs: readonly string[];
}

export type RouteRejectionReason =
  CapabilityRejectionReason | "missing_governance_evidence" | "machine_model_not_observed" | "machine_model_version_mismatch";

export type RouteDecision =
  | { readonly kind: "ROUTED"; readonly capability: CapabilityName; readonly candidate: RouteCandidate; readonly evidenceRefs: readonly string[] }
  | { readonly kind: "DENIED"; readonly reason: "no_eligible_route"; readonly rejections: readonly RouteRejection[] };

export interface RouteRequest {
  readonly capability: CapabilityName;
  readonly candidates: readonly RouteCandidate[];
  readonly machineEvidence: readonly MachineCapabilityEvidence[];
  readonly governanceEvidence: Readonly<Record<string, GovernanceEvidence>>;
}

export interface RouteRejection {
  readonly providerId: string;
  readonly modelId: string;
  readonly reason: RouteRejectionReason;
}

function machineEvidenceFor(candidate: RouteCandidate, evidence: readonly MachineCapabilityEvidence[]) {
  return evidence.find((item) =>
    item.providerId === candidate.providerId &&
    item.modelId === candidate.modelId &&
    (!candidate.modelVersion || item.modelVersion === candidate.modelVersion) &&
    item.modelPresent &&
    item.providerReachable,
  );
}

function governanceFor(candidate: RouteCandidate, evidence: Readonly<Record<string, GovernanceEvidence>>) {
  return evidence[`${candidate.providerId}:${candidate.modelId}`] ?? evidence[candidate.providerId];
}

function admissionFor(candidate: RouteCandidate, governance: GovernanceEvidence): CapabilityAdmission {
  return evaluateCapabilityCandidate(candidate, { allowedCostClasses: governance.allowedCostClasses });
}

function rejectionFor(candidate: RouteCandidate, reason: RouteRejectionReason): RouteRejection {
  return { providerId: candidate.providerId, modelId: candidate.modelId, reason };
}

export function evaluateRouteCandidate(candidate: RouteCandidate, governance?: GovernanceEvidence): CapabilityAdmission {
  return governance ? admissionFor(candidate, governance) : evaluateCapabilityCandidate(candidate);
}
export function routeCapability(request: RouteRequest): RouteDecision {
  const rejections: RouteRejection[] = [];
  const eligible: Array<{ candidate: RouteCandidate; machine: MachineCapabilityEvidence }> = [];

  for (const candidate of request.candidates) {
    if (candidate.capability !== request.capability) {
      rejections.push(rejectionFor(candidate, "capability_unavailable"));
      continue;
    }
    const governance = governanceFor(candidate, request.governanceEvidence);
    if (!governance || !governance.evidenceComplete || governance.evidenceRefs.length === 0) {
      rejections.push(rejectionFor(candidate, "missing_governance_evidence"));
      continue;
    }
    const machine = machineEvidenceFor(candidate, request.machineEvidence);
    if (!machine) {
      const sameModel = request.machineEvidence.find(
        (item) => item.providerId === candidate.providerId && item.modelId === candidate.modelId && item.modelPresent,
      );
      rejections.push(rejectionFor(candidate, sameModel ? "machine_model_version_mismatch" : "machine_model_not_observed"));
      continue;
    }

    const governanceBoundCandidate: RouteCandidate = {
      ...candidate,
      currentness: governance.currentness,
      qualification: governance.qualification,
      licence: governance.licence,
      hardware: governance.hardware,
      evidenceComplete: governance.evidenceComplete,
      health: machine.health ?? (machine.providerReachable ? candidate.health : "UNHEALTHY"),
    };
    const admission = admissionFor(governanceBoundCandidate, governance);
    if (!admission.eligible) {
      rejections.push(rejectionFor(candidate, admission.reason));
      continue;
    }
    eligible.push({ candidate: governanceBoundCandidate, machine });
  }

  if (eligible.length === 0) {
    return { kind: "DENIED", reason: "no_eligible_route", rejections };
  }

  eligible.sort((a, b) =>
    (b.candidate.priority ?? 0) - (a.candidate.priority ?? 0) ||
    `${a.candidate.providerId}:${a.candidate.modelId}`.localeCompare(
      `${b.candidate.providerId}:${b.candidate.modelId}`,
    ),
  );
  const selected = eligible[0];
  return {
    kind: "ROUTED",
    capability: request.capability,
    candidate: selected.candidate,
    evidenceRefs: [
      ...governanceFor(selected.candidate, request.governanceEvidence)!.evidenceRefs,
      ...selected.machine.evidenceRefs,
    ],
  };
}
