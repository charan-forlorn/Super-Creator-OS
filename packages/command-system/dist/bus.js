import { parseProject } from "@haios/project-model";
import { CommandBusValidationError } from "./types.js";
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
export class CommandBus {
    registry;
    state;
    undoStack = [];
    redoStack = [];
    constructor(registry, state) {
        this.registry = registry;
        this.state = state;
    }
    get project() {
        return this.state;
    }
    get canUndo() {
        return this.undoStack.length > 0;
    }
    get canRedo() {
        return this.redoStack.length > 0;
    }
    /**
     * Execute a command. `payload` is validated structurally against the command's
     * registered schema (if any) BEFORE any mutation. Returns the command result.
     * On validation or execution failure, state is unchanged (fail-closed).
     */
    execute(type, payload) {
        const command = this.registry.get(type);
        if (command.schema) {
            const parsed = command.schema.safeParse(payload);
            if (!parsed.success) {
                throw new CommandBusValidationError(type, `payload validation failed: ${parsed.error.message}`);
            }
            payload = parsed.data;
        }
        const { next, inverse, result } = command.execute(this.state, payload);
        // Re-validate the produced project so a buggy command cannot corrupt state.
        this.apply(next);
        this.undoStack.push({ type, payload, inverse, at: Date.now() });
        // BRANCHING: a new edit invalidates the redo future.
        this.redoStack = [];
        return result;
    }
    /**
     * Pure state transition: validate+replace. Shared by execute/undo/redo so
     * none of them accidentally mutates the history stacks.
     */
    apply(next) {
        this.state = parseProject(JSON.parse(JSON.stringify(next)));
    }
    undo() {
        const entry = this.undoStack.pop();
        if (!entry)
            return false;
        const { next } = entry.inverse.execute(this.state, entry.payload);
        this.apply(next);
        this.redoStack.push(entry);
        return true;
    }
    redo() {
        const entry = this.redoStack.pop();
        if (!entry)
            return false;
        // Redo re-applies the FORWARD command, not its inverse. The recorded
        // `inverse` is the undo closure; replaying it here would re-undo.
        const command = this.registry.get(entry.type);
        const { next, inverse } = command.execute(this.state, entry.payload);
        this.apply(next);
        this.undoStack.push({ ...entry, inverse });
        return true;
    }
    /** Replace state (e.g. on project open). Clears both stacks. */
    load(project) {
        this.state = parseProject(JSON.parse(JSON.stringify(project)));
        this.undoStack = [];
        this.redoStack = [];
    }
}
//# sourceMappingURL=bus.js.map