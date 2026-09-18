import { type ProductionExecutionTelemetry } from "./productionTelemetry.js";
export interface QualifiedModelBinding {
    readonly digest: string;
    readonly qualification: "QUALIFIED";
}
export interface QualificationBinding {
    readonly sourceRepo: string;
    readonly sourceCommit: string;
    readonly sourcePath: string;
    readonly sourceSha256: string;
    readonly models: Readonly<Record<string, QualifiedModelBinding>>;
}
export interface GovernedProductionLoopInput {
    readonly instruction: string;
    readonly context?: {
        readonly clipIds?: readonly string[];
        readonly selectedClipId?: string;
        readonly projectSummary?: string;
    };
    readonly baseUrl: string;
    readonly evidenceDir: string;
    readonly qualification: QualificationBinding;
    readonly modelOverride?: string;
    /** Test seam; production uses the real global fetch. */
    readonly fetchImpl?: typeof fetch;
}
export interface GovernedProductionLoopResult {
    readonly status: "COMPLETED" | "DENIED" | "FAILED";
    readonly loopRunId: string;
    readonly routeDecisionId: string;
    readonly evidencePath: string;
    readonly evidenceSha256: string;
    readonly selectedModel?: string;
    readonly telemetry: ProductionExecutionTelemetry | null;
    readonly plan?: unknown;
    readonly error?: string;
}
export declare function runGovernedProductionLoop(input: GovernedProductionLoopInput): Promise<GovernedProductionLoopResult>;
