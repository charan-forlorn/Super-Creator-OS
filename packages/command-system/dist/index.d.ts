import { CommandRegistry } from "./registry.js";
import { CommandBus } from "./bus.js";
import type { Project } from "@haios/project-model";
export * from "./types.js";
export * from "./registry.js";
export * from "./bus.js";
export * from "./commands.js";
/** Register the canonical studio command set into a fresh registry. */
export declare function createStudioRegistry(): CommandRegistry;
export declare function createCommandBus(initial: Project): CommandBus;
//# sourceMappingURL=index.d.ts.map