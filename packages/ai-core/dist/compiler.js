import { CommandError } from "@haios/command-system";
import { aiEditPlanSchema, AI_TOOL_NAMES } from "./plan.js";
export class AiSemanticError extends Error {
    constructor(message) {
        super(message);
        this.name = "AiSemanticError";
    }
}
/** The canonical tool -> command-type mapping. The AI may only produce tools
 *  that resolve to a REGISTERED command. */
const TOOL_TO_COMMAND = {
    split_clip: "clip.split",
    move_clip: "clip.move",
    trim_clip: "clip.trim",
    delete_clip: "clip.delete",
    add_caption: "caption.add",
    change_aspect_ratio: "project.changeAspect",
};
/**
 * Semantic validation: ensure the plan is meaningful against the CURRENT
 * project state (real clip ids, valid boundaries, registered commands).
 * Fail-closed: any inconsistency throws. Does not mutate anything.
 */
export function validatePlanSemantics(plan, project) {
    let targetClipId = null;
    if (plan.target.kind === "clip") {
        targetClipId = plan.target.clipId;
        const exists = project.tracks.some((t) => t.clips.some((c) => c.id === targetClipId));
        if (!exists) {
            throw new AiSemanticError(`AI referenced non-existent clip id '${targetClipId}'`);
        }
    }
    for (const op of plan.operations) {
        if (!AI_TOOL_NAMES.includes(op.tool)) {
            throw new AiSemanticError(`AI hallucinated unknown tool '${op.tool}'`);
        }
        const commandType = TOOL_TO_COMMAND[op.tool];
        if (!commandType) {
            throw new AiSemanticError(`tool '${op.tool}' has no registered command`);
        }
        if (targetClipId && (op.tool === "split_clip" || op.tool === "move_clip" || op.tool === "trim_clip" || op.tool === "delete_clip")) {
            op.params = { ...op.params, clipId: targetClipId };
        }
        validateOperationAgainstProject(op, project);
    }
}
function requireParam(op, key) {
    if (!(key in op.params)) {
        throw new AiSemanticError(`operation '${op.tool}' missing required param '${key}'`);
    }
    return op.params[key];
}
function validateOperationAgainstProject(op, project) {
    const clipId = op.params.clipId;
    if (clipId) {
        const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === clipId);
        if (!clip)
            throw new AiSemanticError(`operation '${op.tool}' targets missing clip '${clipId}'`);
        if (op.tool === "split_clip") {
            const t = Number(requireParam(op, "t"));
            if (!(t > 0 && t < clip.duration)) {
                throw new AiSemanticError(`split point ${t} invalid for clip duration ${clip.duration}`);
            }
        }
        if (op.tool === "trim_clip") {
            const newInPoint = Number(op.params.newInPoint ?? clip.inPoint);
            if (newInPoint < 0)
                throw new AiSemanticError(`trim inPoint ${newInPoint} < 0`);
        }
    }
}
/**
 * Compile a validated plan into a sequence of registered CommandBus commands.
 * The compiler emits ONLY command types present in the registry, so even a
 * semantically-passing plan cannot route to an unregistered mutation.
 */
export function compilePlanToCommands(plan, registry) {
    const commands = [];
    for (const op of plan.operations) {
        const commandType = TOOL_TO_COMMAND[op.tool];
        if (!registry.has(commandType)) {
            throw new CommandError(`refusing to compile unregistered command '${commandType}'`);
        }
        commands.push({ commandType, payload: { ...op.params } });
    }
    return commands;
}
/** Convenience: validate + compile in one call. Returns the command list. */
export function planToCommands(raw, project, registry) {
    const plan = aiEditPlanSchema.parse(raw); // structural
    validatePlanSemantics(plan, project); // semantic
    return compilePlanToCommands(plan, registry);
}
//# sourceMappingURL=compiler.js.map