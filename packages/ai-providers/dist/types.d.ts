import type { AiEditPlan } from "@haios/ai-core";
export type ProviderKind = "ollama" | "openai-compatible" | "hermes";
export interface ProviderRequest {
    /** Natural-language instruction from the user. */
    instruction: string;
    /** The current project context the model may use to ground its plan. */
    context: {
        clipIds: string[];
        selectedClipId?: string;
        projectSummary?: string;
    };
    /** Abort signal for cancellation. */
    signal?: AbortSignal;
}
export interface ProviderResponse {
    /** Structured plan ONLY. Never raw mutation text. */
    plan: AiEditPlan;
    /** Which provider produced it (for telemetry / failover). */
    provider: ProviderKind;
    /** Raw model text, kept for audit only — NEVER executed. */
    rawText?: string;
}
export interface AIProvider {
    readonly kind: ProviderKind;
    /** Whether the provider is reachable/configured. */
    isAvailable(): Promise<boolean>;
    /** Generate a structured plan from a natural-language instruction. */
    generate(req: ProviderRequest): Promise<ProviderResponse>;
}
export declare class ProviderUnavailableError extends Error {
    readonly provider: ProviderKind;
    constructor(provider: ProviderKind, message: string);
}
/**
 * The system prompt we send to every text model. It forces the model to emit
 * ONLY the JSON schema for AiEditPlan. Used by Ollama / OpenAI-compat / Hermes
 * adapters so the models all speak the same contract.
 */
export declare const AI_PLAN_SYSTEM_PROMPT = "You are a video editor assistant. Respond with a SINGLE JSON object matching this schema and nothing else:\n\n{\n  \"version\": 1,\n  \"target\": { \"kind\": \"selection\" } | { \"kind\": \"clip\", \"clipId\": string },\n  \"operations\": [\n    { \"tool\": \"split_clip\"|\"move_clip\"|\"trim_clip\"|\"delete_clip\"|\"add_caption\"|\"change_aspect_ratio\", \"params\": { ... }, \"rationale\"?: string }\n  ]\n}\n\nRules:\n- Only use the listed tools.\n- For split_clip, params.t is seconds from the clip start and must satisfy 0 < t < clip duration.\n- For move_clip, params.newStart is the new timeline start in seconds.\n- For trim_clip, params.newInPoint is the new source in-point in seconds.\n- Never invent clip ids; use the provided selection/target.\n- Output JSON only. No prose, no code fences.";
//# sourceMappingURL=types.d.ts.map