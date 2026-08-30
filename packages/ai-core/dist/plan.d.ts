import { z } from "zod";
/**
 * The AI NEVER emits raw mutations. It emits a structured AIEditPlan. Only
 * registered tool names are allowed; any unknown tool is rejected
 * (hallucination fail-closed).
 */
export declare const AI_TOOL_NAMES: readonly ["split_clip", "move_clip", "trim_clip", "delete_clip", "add_caption", "change_aspect_ratio"];
export type AiToolName = (typeof AI_TOOL_NAMES)[number];
export declare const aiOperationSchema: z.ZodObject<{
    tool: z.ZodEnum<["split_clip", "move_clip", "trim_clip", "delete_clip", "add_caption", "change_aspect_ratio"]>;
    params: z.ZodRecord<z.ZodString, z.ZodUnion<[z.ZodString, z.ZodNumber, z.ZodBoolean]>>;
    /** Free-text rationale (human readable, never executed). */
    rationale: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    params: Record<string, string | number | boolean>;
    tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
    rationale?: string | undefined;
}, {
    params: Record<string, string | number | boolean>;
    tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
    rationale?: string | undefined;
}>;
export type AiOperation = z.infer<typeof aiOperationSchema>;
export declare const aiEditPlanSchema: z.ZodObject<{
    version: z.ZodLiteral<1>;
    /** Which clip the operations target; `selection` resolves to the current selection. */
    target: z.ZodUnion<[z.ZodObject<{
        kind: z.ZodLiteral<"selection">;
    }, "strip", z.ZodTypeAny, {
        kind: "selection";
    }, {
        kind: "selection";
    }>, z.ZodObject<{
        kind: z.ZodLiteral<"clip">;
        clipId: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        kind: "clip";
        clipId: string;
    }, {
        kind: "clip";
        clipId: string;
    }>]>;
    operations: z.ZodArray<z.ZodObject<{
        tool: z.ZodEnum<["split_clip", "move_clip", "trim_clip", "delete_clip", "add_caption", "change_aspect_ratio"]>;
        params: z.ZodRecord<z.ZodString, z.ZodUnion<[z.ZodString, z.ZodNumber, z.ZodBoolean]>>;
        /** Free-text rationale (human readable, never executed). */
        rationale: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        params: Record<string, string | number | boolean>;
        tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
        rationale?: string | undefined;
    }, {
        params: Record<string, string | number | boolean>;
        tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
        rationale?: string | undefined;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    version: 1;
    target: {
        kind: "selection";
    } | {
        kind: "clip";
        clipId: string;
    };
    operations: {
        params: Record<string, string | number | boolean>;
        tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
        rationale?: string | undefined;
    }[];
}, {
    version: 1;
    target: {
        kind: "selection";
    } | {
        kind: "clip";
        clipId: string;
    };
    operations: {
        params: Record<string, string | number | boolean>;
        tool: "split_clip" | "move_clip" | "trim_clip" | "delete_clip" | "add_caption" | "change_aspect_ratio";
        rationale?: string | undefined;
    }[];
}>;
export type AiEditPlan = z.infer<typeof aiEditPlanSchema>;
/** Parse + structurally validate a raw model payload. Throws on malformed JSON. */
export declare function parseAiPlan(raw: unknown): AiEditPlan;
export declare class AiPlanValidationError extends Error {
    constructor(message: string);
}
//# sourceMappingURL=plan.d.ts.map