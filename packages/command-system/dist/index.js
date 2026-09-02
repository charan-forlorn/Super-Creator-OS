import { CommandRegistry } from "./registry.js";
import { CommandBus } from "./bus.js";
import { addAssetCommand, removeAssetCommand, addClipCommand, deleteClipCommand, moveClipCommand, moveAcrossTracksCommand, trimClipCommand, rippleDeleteClipsCommand, rippleTrimClipCommand, setClipAudioCommand, setClipEffectsCommand, setClipSpeedCommand, setClipTransitionCommand, setClipTransformCommand, splitClipCommand, addCaptionCommand, placeCaptionCommand, removeCaptionCommand, changeAspectCommand, addTrackCommand, removeTrackCommand, reorderTrackCommand, setTrackControlsCommand, placeProbedMediaCommand, timelineInsertAssetCommand, timelineOverwriteAssetCommand, relinkMediaCommand, } from "./commands.js";
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
        moveAcrossTracksCommand,
        trimClipCommand,
        rippleDeleteClipsCommand,
        rippleTrimClipCommand,
        setClipAudioCommand,
        setClipEffectsCommand,
        setClipSpeedCommand,
        setClipTransitionCommand,
        setClipTransformCommand,
        splitClipCommand,
        addCaptionCommand,
        placeCaptionCommand,
        removeCaptionCommand,
        changeAspectCommand,
        addTrackCommand,
        removeTrackCommand,
        reorderTrackCommand,
        setTrackControlsCommand,
        placeProbedMediaCommand,
        timelineInsertAssetCommand,
        timelineOverwriteAssetCommand,
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