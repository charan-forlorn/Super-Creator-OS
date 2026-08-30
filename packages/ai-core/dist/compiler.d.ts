import type { Project } from "@haios/project-model";
import { CommandRegistry } from "@haios/command-system";
import { type AiEditPlan } from "./plan.js";
export declare class AiSemanticError extends Error {
    constructor(message: string);
}
export interface CompiledCommand {
    commandType: string;
    payload: Record<string, unknown>;
}
/**
 * Semantic validation: ensure the plan is meaningful against the CURRENT
 * project state (real clip ids, valid boundaries, registered commands).
 * Fail-closed: any inconsistency throws. Does not mutate anything.
 */
export declare function validatePlanSemantics(plan: AiEditPlan, project: Project): void;
/**
 * Compile a validated plan into a sequence of registered CommandBus commands.
 * The compiler emits ONLY command types present in the registry, so even a
 * semantically-passing plan cannot route to an unregistered mutation.
 */
export declare function compilePlanToCommands(plan: AiEditPlan, registry: CommandRegistry): CompiledCommand[];
/** Convenience: validate + compile in one call. Returns the command list. */
export declare function planToCommands(raw: unknown, project: Project, registry: CommandRegistry): CompiledCommand[];
//# sourceMappingURL=compiler.d.ts.map