export interface ProductionExecutionTelemetry {
    readonly schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1";
    readonly loopRunId: string;
    readonly routeDecisionId: string;
    readonly observedAt: string;
    readonly startedAt: string;
    readonly completedAt: string;
    readonly durationMs: number;
    readonly capabilityId: string;
    readonly providerId: string;
    readonly modelId: string;
    readonly modelVersion?: string;
    readonly status: "COMPLETED" | "FAILED";
    readonly generationStatus: "COMPLETED" | "FAILED";
    readonly executionStatus: "NOT_RUN" | "COMPLETED" | "FAILED";
    readonly executedCommandTypes?: readonly string[];
    readonly projectBeforeSha256?: string;
    readonly projectAfterSha256?: string;
    readonly executionDurationMs?: number;
    readonly responseBytes?: number;
    readonly responseSha256?: string;
    /** Hash of the generation/routing contract that produced this observation. */
    readonly contractRevision: string;
    readonly requestSha256: string;
    readonly fallbackUsed: false;
    readonly error?: string;
    readonly evidenceRefs: readonly string[];
}
export interface ProductionEvidence {
    readonly schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1";
    readonly loopRunId: string;
    readonly routeDecisionId: string;
    readonly observedAt: string;
    readonly routeDecision: unknown;
    readonly qualification: {
        readonly sourceRepo: string;
        readonly sourceCommit: string;
        readonly sourcePath: string;
        readonly sourceSha256: string;
        readonly modelDigest: string;
    };
    readonly telemetry: ProductionExecutionTelemetry | null;
    readonly verification: {
        readonly status: "PASS" | "FAIL" | "NOT_RUN";
        readonly planSchemaValidated: boolean;
        readonly operationCount?: number;
        readonly reason?: string;
    };
    readonly evidenceSha256: string;
}
export declare function sha256(value: string): string;
export declare function sealEvidence(payload: Omit<ProductionEvidence, "evidenceSha256">): ProductionEvidence;
export declare function writeProductionEvidence(evidenceDir: string, payload: Omit<ProductionEvidence, "evidenceSha256">): Promise<{
    path: string;
    evidenceSha256: string;
}>;
export declare function loadProductionHistory(evidenceDir: string): Promise<ProductionExecutionTelemetry[]>;
export declare function summarizeModelHistory(rows: readonly ProductionExecutionTelemetry[], providerId: string, modelId: string, contractRevision?: string): Pick<ProductionExecutionTelemetry, "status"> & {
    successRate?: number;
    observedLatencyMs?: number;
};
