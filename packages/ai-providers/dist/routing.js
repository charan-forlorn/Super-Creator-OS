import { evaluateCapabilityCandidate, } from "./capabilities.js";
function machineEvidenceFor(candidate, evidence) {
    return evidence.find((item) => item.providerId === candidate.providerId &&
        item.modelId === candidate.modelId &&
        (!candidate.modelVersion || item.modelVersion === candidate.modelVersion) &&
        item.modelPresent &&
        item.providerReachable);
}
function governanceFor(candidate, evidence) {
    return evidence[`${candidate.providerId}:${candidate.modelId}`] ?? evidence[candidate.providerId];
}
function admissionFor(candidate, governance) {
    return evaluateCapabilityCandidate(candidate, { allowedCostClasses: governance.allowedCostClasses });
}
function rejectionFor(candidate, reason) {
    return { providerId: candidate.providerId, modelId: candidate.modelId, reason };
}
export function evaluateRouteCandidate(candidate, governance) {
    return governance ? admissionFor(candidate, governance) : evaluateCapabilityCandidate(candidate);
}
export function routeCapability(request) {
    const rejections = [];
    const eligible = [];
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
            const sameModel = request.machineEvidence.find((item) => item.providerId === candidate.providerId && item.modelId === candidate.modelId && item.modelPresent);
            rejections.push(rejectionFor(candidate, sameModel ? "machine_model_version_mismatch" : "machine_model_not_observed"));
            continue;
        }
        const governanceBoundCandidate = {
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
        return {
            kind: "DENIED",
            reason: "no_eligible_route",
            rejections,
            routeDecisionId: request.routeDecisionId,
            loopRunId: request.loopRunId,
        };
    }
    eligible.sort((a, b) => {
        const priorityDelta = (b.candidate.priority ?? 0) - (a.candidate.priority ?? 0);
        if (priorityDelta !== 0)
            return priorityDelta;
        const aSuccess = a.candidate.observedSuccessRate;
        const bSuccess = b.candidate.observedSuccessRate;
        if (aSuccess !== undefined && bSuccess !== undefined && aSuccess !== bSuccess) {
            return bSuccess - aSuccess;
        }
        const aLatency = a.candidate.observedLatencyMs;
        const bLatency = b.candidate.observedLatencyMs;
        if (aLatency !== undefined && bLatency !== undefined && aLatency !== bLatency) {
            return aLatency - bLatency;
        }
        const aKey = a.candidate.providerId + ":" + a.candidate.modelId;
        const bKey = b.candidate.providerId + ":" + b.candidate.modelId;
        return aKey.localeCompare(bKey);
    });
    const selected = eligible[0];
    return {
        kind: "ROUTED",
        capability: request.capability,
        candidate: selected.candidate,
        routeDecisionId: request.routeDecisionId,
        loopRunId: request.loopRunId,
        evidenceRefs: [
            ...governanceFor(selected.candidate, request.governanceEvidence).evidenceRefs,
            ...selected.machine.evidenceRefs,
        ],
    };
}
