import type { Project } from "@haios/project-model";
/** A command is the ONLY way to mutate a project. AI and GUI both use it. */
export interface EditCommand<C extends object = object, R = unknown> {
    readonly type: string;
    /** Stable schema for the command payload (used by AI plan compiler). */
    readonly schema?: unknown;
    /**
     * Apply the command to the project, returning the next project and an
     * explicit inverse command for undo. Pure: never mutate `prev`.
     */
    execute(prev: Project, payload: C): {
        next: Project;
        inverse: EditCommand;
        result?: R;
    };
}
export declare class CommandError extends Error {
    constructor(message: string);
}
export declare class CommandBusValidationError extends Error {
    readonly commandType: string;
    readonly reason: string;
    constructor(commandType: string, reason: string);
}
//# sourceMappingURL=types.d.ts.map