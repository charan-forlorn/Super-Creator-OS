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
  execute(prev: Project, payload: C): { next: Project; inverse: EditCommand; result?: R };
}

export class CommandError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CommandError";
  }
}

export class CommandBusValidationError extends Error {
  constructor(
    public readonly commandType: string,
    public readonly reason: string,
  ) {
    super(`Command '${commandType}' rejected: ${reason}`);
    this.name = "CommandBusValidationError";
  }
}
