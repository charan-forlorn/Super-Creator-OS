export async function probeOllamaMachineEvidence(options) {
    const fetchImpl = options.fetchImpl ?? fetch;
    try {
        const response = await fetchImpl(`${options.baseUrl}/api/tags`, {
            signal: AbortSignal.timeout(3000),
        });
        if (!response.ok)
            return unreachable(options);
        const body = (await response.json());
        const models = (body.models ?? [])
            .filter((model) => typeof model.name === "string" && model.name.length > 0)
            .map((model) => ({ modelId: model.name, modelVersion: model.digest }));
        return {
            observedAt: options.observedAt,
            providerId: "ollama",
            providerReachable: true,
            health: "HEALTHY",
            models,
            evidenceRefs: [options.evidenceRef],
        };
    }
    catch {
        return unreachable(options);
    }
}
function unreachable(options) {
    return {
        observedAt: options.observedAt,
        providerId: "ollama",
        providerReachable: false,
        health: "UNHEALTHY",
        models: [],
        evidenceRefs: [options.evidenceRef],
    };
}
export function toMachineCapabilityEvidence(evidence) {
    return evidence.models.map((model) => ({
        observedAt: evidence.observedAt,
        providerId: evidence.providerId,
        providerReachable: evidence.providerReachable,
        modelId: model.modelId,
        modelVersion: model.modelVersion,
        modelPresent: true,
        health: evidence.health,
        evidenceRefs: evidence.evidenceRefs,
    }));
}
