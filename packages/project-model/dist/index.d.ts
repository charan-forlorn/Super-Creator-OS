import { type Project } from "./schema.js";
export { parseProject, projectSchema, PROJECT_SCHEMA_VERSION } from "./schema.js";
export * from "./schema.js";
export * from "./clip-math.js";
export * from "./composition.js";
export declare function createEmptyProject(name: string, id: string): Project;
/** Re-validate a parsed project; returns the same object if valid. */
export declare function assertValidProject(p: Project): Project;
//# sourceMappingURL=index.d.ts.map