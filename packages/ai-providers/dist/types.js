export class ProviderUnavailableError extends Error {
    provider;
    constructor(provider, message) {
        super(`AI provider '${provider}' unavailable: ${message}`);
        this.provider = provider;
        this.name = "ProviderUnavailableError";
    }
}
/**
 * The system prompt we send to every text model. It forces the model to emit
 * ONLY the JSON schema for AiEditPlan. Used by Ollama / OpenAI-compat / Hermes
 * adapters so the models all speak the same contract.
 */
export const AI_PLAN_SYSTEM_PROMPT = `You are a video editor assistant. Respond with a SINGLE JSON object matching this schema and nothing else:

{
  "version": 1,
  "target": { "kind": "selection" } | { "kind": "clip", "clipId": string },
  "operations": [
    { "tool": "split_clip"|"move_clip"|"trim_clip"|"delete_clip"|"add_caption"|"change_aspect_ratio", "params": { ... }, "rationale"?: string }
  ]
}

Rules:
- Only use the listed tools.
- For split_clip, params.t is seconds from the clip start and must satisfy 0 < t < clip duration.
- For move_clip, params.newStart is the new timeline start in seconds.
- For trim_clip, params.newInPoint is the new source in-point in seconds.
- Never invent clip ids; use the provided selection/target.
- Output JSON only. No prose, no code fences.`;
//# sourceMappingURL=types.js.map