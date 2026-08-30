import { CommandError, CommandBusValidationError, } from "./types.js";
/**
 * Central registry of edit commands. Every mutation (GUI or AI) must be a
 * registered command. Unknown command types are rejected fail-closed.
 */
export class CommandRegistry {
    commands = new Map();
    register(command) {
        if (this.commands.has(command.type)) {
            throw new CommandError(`Command '${command.type}' already registered`);
        }
        this.commands.set(command.type, command);
    }
    has(type) {
        return this.commands.has(type);
    }
    get(type) {
        const c = this.commands.get(type);
        if (!c) {
            throw new CommandBusValidationError(type, "unknown command type");
        }
        return c;
    }
    list() {
        return [...this.commands.keys()];
    }
}
//# sourceMappingURL=registry.js.map