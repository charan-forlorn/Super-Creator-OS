import { CommandRegistry } from "./registry.js";
import { CommandBus } from "./bus.js";
import type { Project } from "@haios/project-model";
import {
  addAssetCommand,
  removeAssetCommand,
  addClipCommand,
  deleteClipCommand,
  moveClipCommand,
  trimClipCommand,
  setClipAudioCommand,
  setClipEffectsCommand,
  setClipTransitionCommand,
  setClipTransformCommand,
  splitClipCommand,
  addCaptionCommand,
  placeCaptionCommand,
  removeCaptionCommand,
  changeAspectCommand,
  addTrackCommand,
  removeTrackCommand,
  placeProbedMediaCommand,
  relinkMediaCommand,
} from "./commands.js";
import type { EditCommand } from "./types.js";

export * from "./types.js";
export * from "./registry.js";
export * from "./bus.js";
export * from "./commands.js";

/** Register the canonical studio command set into a fresh registry. */
export function createStudioRegistry(): CommandRegistry {
  const reg = new CommandRegistry();
  const cmds: EditCommand[] = [
    addAssetCommand,
    removeAssetCommand,
    addClipCommand,
    deleteClipCommand,
    moveClipCommand,
    trimClipCommand,
    setClipAudioCommand,
    setClipEffectsCommand,
    setClipTransitionCommand,
    setClipTransformCommand,
    splitClipCommand,
    addCaptionCommand,
    placeCaptionCommand,
    removeCaptionCommand,
    changeAspectCommand,
    addTrackCommand,
    removeTrackCommand,
    placeProbedMediaCommand,
    relinkMediaCommand,
  ];
  for (const c of cmds) reg.register(c);
  return reg;
}

export function createCommandBus(initial: Project): CommandBus {
  return new CommandBus(createStudioRegistry(), initial);
}
