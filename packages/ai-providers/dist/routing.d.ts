import { type CapabilityAdmission, type CapabilityName, type CapabilityRejectionReason, type CostClass, type CurrentnessState, type HealthState, type QualificationState, type LicenceState, type HardwareFit } from "./capabilities.js";
export interface RouteCandidate {
    capability: CapabilityName;
    providerId: string;
    modelId: string;
    modelVersion?: string;
    /** Stable capability identity used by governed production routing. */
    capabilityId?: string;
    capabilityVersion?: string;
    capabilityKind?: string;
    authorityScope?: string;
    costClass: CostClass;
    availability: "READY" | "PARTIAL" | "ADAPTER_ONLY" | "EXTERNAL" | "LOCAL_NO_MODEL" | "PLANNED" | "BLOCKED" | "UNKNOWN";
    currentness: CurrentnessState;
    health: HealthState;
    qualification: QualificationState;
    licence: LicenceState;
    hardware: HardwareFit;
    evidenceComplete: boolean;
    priority?: number;
    /** Observed production-loop history; omitted when no real telemetry exists. */
    observedSuccessRate?: number;
    observedLatencyMs?: number;
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
export type RouteRejectionReason = CapabilityRejectionReason | "missing_governance_evidence" | "machine_model_not_observed" | "machine_model_version_mismatch";
export type RouteDecision = {
    readonly kind: "ROUTED";
    readonly capability: CapabilityName;
    readonly candidate: RouteCandidate;
    readonly evidenceRefs: readonly string[];
    readonly routeDecisionId?: string;
    readonly loopRunId?: string;
} | {
    readonly kind: "DENIED";
    readonly reason: "no_eligible_route";
    readonly rejections: readonly RouteRejection[];
    readonly routeDecisionId?: string;
    readonly loopRunId?: string;
};
export interface RouteRequest {
    readonly capability: CapabilityName;
    readonly candidates: readonly RouteCandidate[];
    readonly routeDecisionId?: string;
    readonly loopRunId?: string;
    readonly machineEvidence: readonly MachineCapabilityEvidence[];
    readonly governanceEvidence: Readonly<Record<string, GovernanceEvidence>>;
}
export interface RouteRejection {
    readonly providerId: string;
    readonly modelId: string;
    readonly reason: RouteRejectionReason;
}
export declare function evaluateRouteCandidate(candidate: RouteCandidate, governance?: GovernanceEvidence): CapabilityAdmission;
export declare function routeCapability(request: RouteRequest): RouteDecision;
//# sourceMappingURL=routing.d.ts.map