import { parseProject, projectSchema, type Project } from "./schema.js";

export { parseProject, projectSchema, PROJECT_SCHEMA_VERSION } from "./schema.js";
export * from "./schema.js";
export * from "./clip-math.js";

export function createEmptyProject(name: string, id: string): Project {
  const now = new Date().toISOString();
  return {
    schemaVersion: 1,
    id,
    name,
    createdAt: now,
    updatedAt: now,
    assets: [],
    tracks: [],
    durationSec: 0,
    aspectRatio: "1920x1080",
  };
}

/** Re-validate a parsed project; returns the same object if valid. */
export function assertValidProject(p: Project): Project {
  return parseProject(projectSchema.parse(p));
}
