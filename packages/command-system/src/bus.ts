import { parseProject, type Project } from "@haios/project-model";
import { CommandRegistry } from "./registry.js";
import { CommandBusValidationError, EditCommand } from "./types.js";

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
  batch(items: BatchItem[]): void {
    if (!Array.isArray(items) || items.length === 0) {
      throw new CommandBusValidationError("batch", "items must be a non-empty array");
    }
    // Phase 1: resolve commands + validate payloads up front (no mutation yet).
    const steps: { entry: ExecutedEntry }[] = [];
    for (const item of items) {
      const command = this.registry.get(item.commandType); // throws on unknown
      let payload = item.payload;
      if (command.schema) {
        const parsed = (command.schema as { safeParse: (v: unknown) => any }).safeParse(payload);
        if (!parsed.success) {
          throw new CommandBusValidationError(
            item.commandType,
            `payload validation failed: ${(parsed.error as { message: string }).message}`,
          );
        }
        payload = parsed.data;
      }
      const { inverse } = command.execute(this.state, payload);
      steps.push({ entry: { type: item.commandType, payload, inverse, at: Date.now() } });
    }
    // Phase 2: re-execute forward against accumulated state. If any throws, the
    // catch leaves `this.state` untouched (we never assigned it before throw).
    let nextState = this.state;
    const applied: ExecutedEntry[] = [];
    try {
      for (const { entry } of steps) {
        const command = this.registry.get(entry.type);
        const { next, inverse } = command.execute(nextState, entry.payload);
        nextState = next;
        applied.push({ ...entry, inverse });
      }
    } catch (e) {
      // Fail closed: discard accumulated work, state is unchanged.
      throw e;
    }
    this.state = parseProject(JSON.parse(JSON.stringify(nextState)));
    // Single undo entry; its logical inverse replays sub-inverses in reverse.
    this.undoStack.push({
      type: "batch",
      payload: applied,
      inverse: batchInverse,
      at: Date.now(),
    });
    this.redoStack = [];
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
    if (entry.type === "batch") {
      // Replay each sub-inverse in REVERSE order (last-applied undone first).
      let s = this.state;
      const subs = entry.payload as ExecutedEntry[];
      for (let i = subs.length - 1; i >= 0; i--) {
        const sub = subs[i];
        const { next } = sub.inverse.execute(s, sub.payload);
        s = next;
      }
      this.apply(s);
      this.redoStack.push(entry);
      return true;
    }
    const { next } = entry.inverse.execute(this.state, entry.payload);
    this.apply(next);
    this.redoStack.push(entry);
    return true;
  }

  redo(): boolean {
    const entry = this.redoStack.pop();
    if (!entry) return false;
    if (entry.type === "batch") {
      // Replay each forward command in FORWARD order.
      let s = this.state;
      const subs = entry.payload as ExecutedEntry[];
      for (const sub of subs) {
        const command = this.registry.get(sub.type);
        const { next, inverse } = command.execute(s, sub.payload);
        s = next;
        sub.inverse = inverse; // refresh in case command re-derives it
      }
      this.apply(s);
      this.undoStack.push(entry);
      return true;
    }
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

/**
 * Inverse of a `batch` entry: stored on the undo stack so a single `undo()`
 * call replays all sub-inverses. The actual replay logic lives in
 * `CommandBus.undo` (batch branch). This marker exists so the undo-entry shape
 * stays uniform (type + inverse) and never produces an invalid inverse chain.
 */
const batchInverse: EditCommand<ExecutedEntry[], unknown> = {
  type: "batch.inverse",
  execute(prev) {
    return { next: prev, inverse: batchInverse };
  },
};
