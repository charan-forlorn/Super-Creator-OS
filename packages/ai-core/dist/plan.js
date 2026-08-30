import { z } from "zod";
/**
 * The AI NEVER emits raw mutations. It emits a structured AIEditPlan. Only
 * registered tool names are allowed; any unknown tool is rejected
 * (hallucination fail-closed).
 */
export const AI_TOOL_NAMES = [
    "split_clip",
    "move_clip",
    "trim_clip",
    "delete_clip",
    "add_caption",
    "change_aspect_ratio",
];
const paramSchema = z.record(z.string(), z.union([z.string(), z.number(), z.boolean()]));
export const aiOperationSchema = z.object({
    tool: z.enum(AI_TOOL_NAMES),
    params: paramSchema,
    /** Free-text rationale (human readable, never executed). */
    rationale: z.string().optional(),
});
export const aiEditPlanSchema = z.object({
    version: z.literal(1),
    /** Which clip the operations target; `selection` resolves to the current selection. */
    target: z.union([z.object({ kind: z.literal("selection") }), z.object({ kind: z.literal("clip"), clipId: z.string() })]),
    operations: z.array(aiOperationSchema).min(1),
});
/** Parse + structurally validate a raw model payload. Throws on malformed JSON. */
export function parseAiPlan(raw) {
    const result = aiEditPlanSchema.safeParse(raw);
    if (!result.success) {
        throw new AiPlanValidationError(`malformed AI plan: ${result.error.message}`);
    }
    return result.data;
}
export class AiPlanValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = "AiPlanValidationError";
    }
}
//# sourceMappingURL=plan.js.map