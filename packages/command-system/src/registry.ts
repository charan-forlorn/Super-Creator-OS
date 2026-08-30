import {
  EditCommand,
  CommandError,
  CommandBusValidationError,
} from "./types.js";

type AnyCommand = EditCommand<any, any>;

/**
 * Central registry of edit commands. Every mutation (GUI or AI) must be a
 * registered command. Unknown command types are rejected fail-closed.
 */
export class CommandRegistry {
  private commands = new Map<string, AnyCommand>();

  register(command: AnyCommand): void {
    if (this.commands.has(command.type)) {
      throw new CommandError(`Command '${command.type}' already registered`);
    }
    this.commands.set(command.type, command);
  }

  has(type: string): boolean {
    return this.commands.has(type);
  }

  get(type: string): AnyCommand {
    const c = this.commands.get(type);
    if (!c) {
      throw new CommandBusValidationError(type, "unknown command type");
    }
    return c;
  }

  list(): string[] {
    return [...this.commands.keys()];
  }
}
