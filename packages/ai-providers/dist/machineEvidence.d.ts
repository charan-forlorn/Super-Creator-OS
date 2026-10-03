export interface OllamaObservedModel {
    readonly modelId: string;
    readonly modelVersion?: string;
}
export interface OllamaMachineEvidence {
    readonly observedAt: string;
    readonly providerId: "ollama";
    readonly providerReachable: boolean;
    readonly health: "HEALTHY" | "UNHEALTHY";
    readonly models: readonly OllamaObservedModel[];
    readonly evidenceRefs: readonly string[];
}
export interface OllamaMachineEvidenceOptions {
    readonly baseUrl: string;
    readonly observedAt: string;
    readonly evidenceRef: string;
    readonly fetchImpl?: typeof fetch;
}
export declare function probeOllamaMachineEvidence(options: OllamaMachineEvidenceOptions): Promise<OllamaMachineEvidence>;
export declare function toMachineCapabilityEvidence(evidence: OllamaMachineEvidence): readonly import("./routing.js").MachineCapabilityEvidence[];
//# sourceMappingURL=machineEvidence.d.ts.map