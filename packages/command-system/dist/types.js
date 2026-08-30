export class CommandError extends Error {
    constructor(message) {
        super(message);
        this.name = "CommandError";
    }
}
export class CommandBusValidationError extends Error {
    commandType;
    reason;
    constructor(commandType, reason) {
        super(`Command '${commandType}' rejected: ${reason}`);
        this.commandType = commandType;
        this.reason = reason;
        this.name = "CommandBusValidationError";
    }
}
//# sourceMappingURL=types.js.map