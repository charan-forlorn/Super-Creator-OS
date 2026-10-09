import type { Project } from "@haios/project-model";
import { CommandRegistry, CommandError } from "@haios/command-system";
import { aiEditPlanSchema, AI_TOOL_NAMES, type AiEditPlan, type AiOperation } from "./plan.js";

export class AiSemanticError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AiSemanticError";
  }
}

/** The canonical tool -> command-type mapping. The AI may only produce tools
 *  that resolve to a REGISTERED command. */
const TOOL_TO_COMMAND: Record<(typeof AI_TOOL_NAMES)[number], string> = {
  split_clip: "clip.split",
  move_clip: "clip.move",
  trim_clip: "clip.trim",
  delete_clip: "clip.delete",
  add_caption: "caption.place",
  change_aspect_ratio: "project.changeAspect",
};

export interface CompiledCommand {
  commandType: string;
  payload: Record<string, unknown>;
}

/** Every resolution the project supports, mapped to its canonical export ratio. */
const ASPECT_RATIO_RESOLUTIONS: Record<string, string> = {
  "1920x1080": "1920x1080",
  "1080x1920": "1080x1920",
  "1080x1080": "1080x1080",
  landscape: "1920x1080",
  vertical: "1080x1920",
  portrait: "1080x1920",
  square: "1080x1080",
  "16:9": "1920x1080",
  "9:16": "1080x1920",
  "1:1": "1080x1080",
};

/**
 * Resolve the canonical `ratio` value for `change_aspect_ratio`.
 *
 * The model names this parameter inconsistently (`ratio`, `aspectRatio`,
 * `aspect`, `resolution`, or nested under `place`). Rather than silently
 * dropping the intent — which left `ratio` undefined and made the CommandBus
 * reject the command — the known aliases are resolved to the single canonical
 * key. An unresolvable value throws (fail-closed) instead of inventing one.
 */
function resolveAspectRatio(params: Record<string, unknown>): string {
  const candidates: unknown[] = [];
  for (const key of ["ratio", "aspectRatio", "aspect_ratio", "aspect", "resolution", "place"]) {
    const value = params[key];
    if (value === undefined) continue;
    if (value !== null && typeof value === "object") {
      const nested = value as Record<string, unknown>;
      for (const nestedKey of ["ratio", "aspectRatio", "aspect_ratio", "aspect", "resolution"]) {
        if (nested[nestedKey] !== undefined) candidates.push(nested[nestedKey]);
      }
      continue;
    }
    candidates.push(value);
  }
  if (candidates.length === 0) {
    throw new AiSemanticError("operation 'change_aspect_ratio' has no resolvable aspect ratio");
  }
  for (const candidate of candidates) {
    if (typeof candidate !== "string") continue;
    const resolved = ASPECT_RATIO_RESOLUTIONS[candidate.trim().toLowerCase()];
    if (resolved) return resolved;
  }
  throw new AiSemanticError(
    `unresolvable aspect ratio ${JSON.stringify(candidates[0])} (expected one of ${Object.keys(ASPECT_RATIO_RESOLUTIONS).join(", ")})`,
  );
}

/**
 * Coerce a numeric caption param a model may emit as a numeric string
 * ("2", "3.5"). A value that is present but cannot become a number throws
 * rather than being forwarded: the CommandBus would reject it anyway, and
 * failing here keeps the compiler's own contract honest (fail-closed).
 */
function coerceNumericParam(params: Record<string, unknown>, key: string): void {
  const value = params[key];
  if (value === undefined) return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new AiSemanticError(`param '${key}' is not a finite number: ${value}`);
    }
    return;
  }
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
    params[key] = Number(value);
    return;
  }
  throw new AiSemanticError(
    `param '${key}' must be a number or numeric string, received ${typeof value}: ${JSON.stringify(value)}`,
  );
}

/**
 * Semantic validation: ensure the plan is meaningful against the CURRENT
 * project state (real clip ids, valid boundaries, registered commands).
 * Fail-closed: any inconsistency throws. Does not mutate anything.
 */
export function validatePlanSemantics(plan: AiEditPlan, project: Project): void {
  let targetClipId: string | null = null;
  if (plan.target.kind === "clip") {
    targetClipId = plan.target.clipId;
    const exists = project.tracks.some((t) => t.clips.some((c) => c.id === targetClipId));
    if (!exists) {
      throw new AiSemanticError(`AI referenced non-existent clip id '${targetClipId}'`);
    }
  }

  for (const op of plan.operations) {
    if (!AI_TOOL_NAMES.includes(op.tool)) {
      throw new AiSemanticError(`AI hallucinated unknown tool '${op.tool}'`);
    }
    const commandType = TOOL_TO_COMMAND[op.tool];
    if (!commandType) {
      throw new AiSemanticError(`tool '${op.tool}' has no registered command`);
    }
    if (targetClipId && (op.tool === "split_clip" || op.tool === "move_clip" || op.tool === "trim_clip" || op.tool === "delete_clip")) {
      op.params = { ...op.params, clipId: targetClipId };
    }
    validateOperationAgainstProject(op, project);
  }
}

function requireParam(op: AiOperation, key: string): unknown {
  if (!(key in op.params)) {
    throw new AiSemanticError(`operation '${op.tool}' missing required param '${key}'`);
  }
  return op.params[key];
}

function validateOperationAgainstProject(op: AiOperation, project: Project): void {
  const clipId = op.params.clipId as string | undefined;
  if (clipId) {
    const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === clipId);
    if (!clip) throw new AiSemanticError(`operation '${op.tool}' targets missing clip '${clipId}'`);
    if (op.tool === "split_clip") {
      const t = Number(requireParam(op, "t"));
      if (!(t > 0 && t < clip.duration)) {
        throw new AiSemanticError(`split point ${t} invalid for clip duration ${clip.duration}`);
      }
    }
    if (op.tool === "trim_clip") {
      const newInPoint = Number(op.params.newInPoint ?? clip.inPoint);
      if (newInPoint < 0) throw new AiSemanticError(`trim inPoint ${newInPoint} < 0`);
    }
  }
}

/**
 * Compile a validated plan into a sequence of registered CommandBus commands.
 * The compiler emits ONLY command types present in the registry, so even a
 * semantically-passing plan cannot route to an unregistered mutation.
 *
 * Payloads are emitted canonically for their target command: alias keys are
 * resolved away and numeric params are coerced to real numbers, so the
 * CommandBus's own schema re-validation accepts them. A payload that cannot be
 * resolved to a canonical form throws here (fail-closed) rather than reaching
 * the bus half-formed — the compiler never invents a value.
 */
export function compilePlanToCommands(
  plan: AiEditPlan,
  registry: CommandRegistry,
): CompiledCommand[] {
  const commands: CompiledCommand[] = [];
  for (const op of plan.operations) {
    const commandType = TOOL_TO_COMMAND[op.tool];
    if (!registry.has(commandType)) {
      throw new CommandError(`refusing to compile unregistered command '${commandType}'`);
    }
    const params = { ...op.params };
    if (op.tool === "add_caption") {
      coerceNumericParam(params, "start");
      coerceNumericParam(params, "duration");
    }
    if (op.tool === "change_aspect_ratio") {
      // Canonical payload: alias keys are resolved away, never forwarded.
      commands.push({ commandType, payload: { ratio: resolveAspectRatio(params) } });
      continue;
    }
    commands.push({ commandType, payload: params });
  }
  return commands;
}

/** Convenience: validate + compile in one call. Returns the command list. */
export function planToCommands(
  raw: unknown,
  project: Project,
  registry: CommandRegistry,
): CompiledCommand[] {
  const plan = aiEditPlanSchema.parse(raw); // structural
  validatePlanSemantics(plan, project); // semantic
  return compilePlanToCommands(plan, registry);
}
