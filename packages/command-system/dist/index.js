import { CommandRegistry } from "./registry.js";
import { CommandBus } from "./bus.js";
import { addAssetCommand, removeAssetCommand, addClipCommand, deleteClipCommand, moveClipCommand, trimClipCommand, setClipAudioCommand, splitClipCommand, addCaptionCommand, placeCaptionCommand, removeCaptionCommand, changeAspectCommand, addTrackCommand, removeTrackCommand, placeProbedMediaCommand, relinkMediaCommand, } from "./commands.js";
export * from "./types.js";
export * from "./registry.js";
export * from "./bus.js";
export * from "./commands.js";
/** Register the canonical studio command set into a fresh registry. */
export function createStudioRegistry() {
    const reg = new CommandRegistry();
    const cmds = [
        addAssetCommand,
        removeAssetCommand,
        addClipCommand,
        deleteClipCommand,
        moveClipCommand,
        trimClipCommand,
        setClipAudioCommand,
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
    for (const c of cmds)
        reg.register(c);
    return reg;
}
export function createCommandBus(initial) {
    return new CommandBus(createStudioRegistry(), initial);
}
//# sourceMappingURL=index.js.map