import { type Project } from "@haios/project-model";
import { CommandRegistry } from "./registry.js";
import { EditCommand } from "./types.js";
export interface ExecutedEntry {
    type: string;
    payload: unknown;
    inverse: EditCommand<any, any>;
    at: number;
}
/**
 * The single shared mutation path for the whole studio.
 *
 * Invariants enforced:
 *  - Every mutation goes through `execute`; no code mutates Project directly.
 *  - Unknown command types are rejected fail-closed.
 *  - Invalid/failed commands never change state.
 *  - Undo replays the recorded inverse.
 *  - Redo stack is cleared whenever a NEW command is executed after an undo
 *    (branching edit semantics).
 */
export declare class CommandBus {
    private registry;
    private state;
    private undoStack;
    private redoStack;
    constructor(registry: CommandRegistry, state: Project);
    get project(): Project;
    get canUndo(): boolean;
    get canRedo(): boolean;
    /**
     * Execute a command. `payload` is validated structurally against the command's
     * registered schema (if any) BEFORE any mutation. Returns the command result.
     * On validation or execution failure, state is unchanged (fail-closed).
     */
    execute<TResult = unknown>(type: string, payload: unknown): TResult;
    /**
     * Pure state transition: validate+replace. Shared by execute/undo/redo so
     * none of them accidentally mutates the history stacks.
     */
    private apply;
    undo(): boolean;
    redo(): boolean;
    /** Replace state (e.g. on project open). Clears both stacks. */
    load(project: Project): void;
}
//# sourceMappingURL=bus.d.ts.map