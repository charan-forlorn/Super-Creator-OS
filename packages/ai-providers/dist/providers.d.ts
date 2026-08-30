import { type AiEditPlan } from "@haios/ai-core";
import { AIProvider, ProviderRequest, ProviderResponse, ProviderKind } from "./types.js";
/** Extract the first balanced JSON object from arbitrary model text. */
export declare function extractJsonObject(text: string): string;
/** Shared: parse the model text into a strict AIEditPlan (never returns raw text as action). */
export declare function modelTextToPlan(rawText: string, _provider: ProviderKind): AiEditPlan;
/**
 * Deterministic, fully-offline provider used for tests, E2E, and when no model
 * is configured. Maps a small set of canonical natural-language commands to
 * plans directly (no network). This lets the whole AI pipeline run and be
 * verified without an external model.
 */
export declare class OfflineProvider implements AIProvider {
    readonly kind: ProviderKind;
    isAvailable(): Promise<boolean>;
    generate(req: ProviderRequest): Promise<ProviderResponse>;
}
interface OllamaConfig {
    baseUrl: string;
    model: string;
    /** Injectable fetch for testing. */
    fetchImpl?: typeof fetch;
}
export declare class OllamaProvider implements AIProvider {
    private cfg;
    readonly kind: ProviderKind;
    constructor(cfg: OllamaConfig);
    isAvailable(): Promise<boolean>;
    generate(req: ProviderRequest): Promise<ProviderResponse>;
}
interface OpenAIConfig {
    baseUrl: string;
    apiKey: string;
    model: string;
    fetchImpl?: typeof fetch;
}
export declare class OpenAICompatibleProvider implements AIProvider {
    private cfg;
    readonly kind: ProviderKind;
    constructor(cfg: OpenAIConfig);
    isAvailable(): Promise<boolean>;
    generate(req: ProviderRequest): Promise<ProviderResponse>;
}
export {};
//# sourceMappingURL=providers.d.ts.map