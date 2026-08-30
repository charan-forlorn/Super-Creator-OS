import { parseProject, type Project } from "@haios/project-model";
import { CommandRegistry } from "./registry.js";
import { CommandBusValidationError, EditCommand } from "./types.js";

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
export class CommandBus {
  private undoStack: ExecutedEntry[] = [];
  private redoStack: ExecutedEntry[] = [];

  constructor(
    private registry: CommandRegistry,
    private state: Project,
  ) {}

  get project(): Project {
    return this.state;
  }

  get canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  get canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  /**
   * Execute a command. `payload` is validated structurally against the command's
   * registered schema (if any) BEFORE any mutation. Returns the command result.
   * On validation or execution failure, state is unchanged (fail-closed).
   */
  execute<TResult = unknown>(type: string, payload: unknown): TResult {
    const command = this.registry.get(type);
    if (command.schema) {
      const parsed = (command.schema as { safeParse: (v: unknown) => any }).safeParse(payload);
      if (!parsed.success) {
        throw new CommandBusValidationError(
          type,
          `payload validation failed: ${(parsed.error as { message: string }).message}`,
        );
      }
      payload = parsed.data;
    }
    const { next, inverse, result } = command.execute(this.state, payload);
    // Re-validate the produced project so a buggy command cannot corrupt state.
    this.apply(next);
    this.undoStack.push({ type, payload, inverse, at: Date.now() });
    // BRANCHING: a new edit invalidates the redo future.
    this.redoStack = [];
    return result as TResult;
  }

  /**
   * Pure state transition: validate+replace. Shared by execute/undo/redo so
   * none of them accidentally mutates the history stacks.
   */
  private apply(next: Project): void {
    this.state = parseProject(JSON.parse(JSON.stringify(next)));
  }

  undo(): boolean {
    const entry = this.undoStack.pop();
    if (!entry) return false;
    const { next } = entry.inverse.execute(this.state, entry.payload);
    this.apply(next);
    this.redoStack.push(entry);
    return true;
  }

  redo(): boolean {
    const entry = this.redoStack.pop();
    if (!entry) return false;
    // Redo re-applies the FORWARD command, not its inverse. The recorded
    // `inverse` is the undo closure; replaying it here would re-undo.
    const command = this.registry.get(entry.type);
    const { next, inverse } = command.execute(this.state, entry.payload);
    this.apply(next);
    this.undoStack.push({ ...entry, inverse });
    return true;
  }

  /** Replace state (e.g. on project open). Clears both stacks. */
  load(project: Project): void {
    this.state = parseProject(JSON.parse(JSON.stringify(project)));
    this.undoStack = [];
    this.redoStack = [];
  }
}
