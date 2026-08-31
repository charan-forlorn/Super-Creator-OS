import { type Project } from "@haios/project-model";
import { CommandRegistry } from "./registry.js";
import { EditCommand } from "./types.js";
export interface ExecutedEntry {
    type: string;
    payload: unknown;
    inverse: EditCommand<any, any>;
    at: number;
}
/** A single sub-command within a batch. */
export interface BatchItem {
    commandType: string;
    payload: unknown;
}
/**
 * The single shared mutation path for the whole studio.
 *
 * Invariants enforced:
 *  - Every mutation goes through `execute`/`batch`; no code mutates Project directly.
 *  - Unknown command types are rejected fail-closed.
 *  - Invalid/failed commands never change state.
 *  - Undo replays the recorded inverse.
 *  - Redo stack is cleared whenever a NEW command is executed after an undo
 *    (branching edit semantics).
 *  - `batch` applies several commands as ONE atomic undo unit, preserving
 *    exact group undo/redo for multi-selection edits.
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
     * Batch: apply several registered sub-commands as ONE atomic, undoable unit.
     *
     * Invariants (consistent with `execute`):
     *  - Every sub-item must be a registered command type (fail-closed otherwise).
     *  - Every sub-payload is schema-validated before ANY mutation.
     *  - If ANY sub-command throws (validation or execution), state is unchanged
     *    and the whole batch is rejected (no partial application).
     *  - The entire batch becomes exactly ONE undo entry. Undo replays each
     *    sub-inverse in REVERSE order; redo replays each forward command in
     *    forward order. This preserves exact group undo/redo semantics for
     *    multi-selection edits (R2.1) without polluting the history stack.
     *  - A new edit after an undo still clears the redo future (branching).
     */
    batch(items: BatchItem[]): void;
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