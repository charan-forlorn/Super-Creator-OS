import { EditCommand } from "./types.js";
type AnyCommand = EditCommand<any, any>;
/**
 * Central registry of edit commands. Every mutation (GUI or AI) must be a
 * registered command. Unknown command types are rejected fail-closed.
 */
export declare class CommandRegistry {
    private commands;
    register(command: AnyCommand): void;
    has(type: string): boolean;
    get(type: string): AnyCommand;
    list(): string[];
}
export {};
//# sourceMappingURL=registry.d.ts.map