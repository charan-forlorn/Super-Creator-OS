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
] as const;
export type AiToolName = (typeof AI_TOOL_NAMES)[number];

/**
 * Producer-side param contract.
 *
 * A real model does not reliably emit typed scalars: it emits numeric strings
 * ("2", "3.5") and occasionally nests an object under an alias
 * (`{ place: { ratio: "1080x1920" } }`). The previous scalar-only union
 * rejected both shapes outright, and the numeric-string case produced a
 * payload the CommandBus then rejected with `invalid_type`.
 *
 * Structural admission is deliberately permissive here — values are still
 * constrained at the command seam by the registered command schema, and the
 * compiler fails closed on anything it cannot resolve (see compiler.ts).
 */
export const aiParamValueSchema: z.ZodType<AiParamValue> = z.lazy(() =>
  z.union([z.string(), z.number(), z.boolean(), z.array(aiParamValueSchema), z.record(z.string(), aiParamValueSchema)]),
);
export type AiParamValue =
  | string
  | number
  | boolean
  | AiParamValue[]
  | { [key: string]: AiParamValue };

const paramSchema = z.record(z.string(), aiParamValueSchema);

export const aiOperationSchema = z.object({
  tool: z.enum(AI_TOOL_NAMES),
  params: paramSchema,
  /** Free-text rationale (human readable, never executed). */
  rationale: z.string().optional(),
});
export type AiOperation = z.infer<typeof aiOperationSchema>;

export const aiEditPlanSchema = z.object({
  version: z.literal(1),
  /** Which clip the operations target; `selection` resolves to the current selection. */
  target: z.union([z.object({ kind: z.literal("selection") }), z.object({ kind: z.literal("clip"), clipId: z.string() })]),
  operations: z.array(aiOperationSchema).min(1),
});
export type AiEditPlan = z.infer<typeof aiEditPlanSchema>;

/** Parse + structurally validate a raw model payload. Throws on malformed JSON. */
export function parseAiPlan(raw: unknown): AiEditPlan {
  const result = aiEditPlanSchema.safeParse(raw);
  if (!result.success) {
    throw new AiPlanValidationError(`malformed AI plan: ${result.error.message}`);
  }
  return result.data;
}

export class AiPlanValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AiPlanValidationError";
  }
}
