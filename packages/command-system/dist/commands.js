import { z } from "zod";
import { exportResolutionSchema, captionSchema, clipSchema, validateClipAgainstAsset, } from "@haios/project-model";
import { CommandError } from "./types.js";
function findClip(project, clipId) {
    for (const track of project.tracks) {
        const clip = track.clips.find((c) => c.id === clipId);
        if (clip)
            return { clip, track };
    }
    throw new CommandError(`CLIP_NOT_FOUND: ${clipId}`);
}
function findAsset(project, assetId) {
    const a = project.assets.find((x) => x.id === assetId);
    if (!a)
        throw new CommandError(`ASSET_NOT_FOUND: ${assetId}`);
    return a;
}
function recomputeDuration(project) {
    let max = 0;
    for (const track of project.tracks) {
        for (const clip of track.clips) {
            max = Math.max(max, clip.start + clip.duration);
        }
    }
    return max;
}
/* ----------------------------- addAsset ----------------------------- */
export const ADD_ASSET = "asset.add";
export const addAssetCommand = {
    type: ADD_ASSET,
    execute(prev, { asset }) {
        if (prev.assets.some((a) => a.id === asset.id)) {
            throw new CommandError(`ASSET_DUPLICATE: ${asset.id}`);
        }
        const next = {
            ...prev,
            assets: [...prev.assets, asset],
            updatedAt: new Date().toISOString(),
        };
        return { next, inverse: removeAssetCommand };
    },
};
export const removeAssetCommand = {
    type: "asset.remove",
    execute(prev, { asset }) {
        const next = {
            ...prev,
            assets: prev.assets.filter((a) => a.id !== asset.id),
            updatedAt: new Date().toISOString(),
        };
        return { next, inverse: addAssetCommand };
    },
};
/* ----------------------------- addClip ------------------------------ */
export const ADD_CLIP = "clip.add";
export const addClipCommand = {
    type: ADD_CLIP,
    execute(prev, { clip }) {
        const asset = findAsset(prev, clip.assetId);
        const bad = validateClipAgainstAsset(clip, asset);
        if (bad)
            throw new CommandError(`INVALID_CLIP: ${bad}`);
        const tracks = prev.tracks.map((t) => t.id === clip.trackId ? { ...t, clips: [...t.clips, clip] } : t);
        const next = {
            ...prev,
            tracks,
            durationSec: Math.max(recomputeDuration({ ...prev, tracks }), prev.durationSec),
            updatedAt: new Date().toISOString(),
        };
        return { next, inverse: { type: DELETE_CLIP, execute: (p) => deleteClipCommand.execute(p, { clipId: clip.id }) } };
    },
};
/* ----------------------------- deleteClip --------------------------- */
export const DELETE_CLIP = "clip.delete";
export const deleteClipCommand = {
    type: DELETE_CLIP,
    execute(prev, { clipId }) {
        const { clip } = findClip(prev, clipId);
        const tracks = prev.tracks.map((t) => t.id === clip.trackId
            ? { ...t, clips: t.clips.filter((c) => c.id !== clipId) }
            : t);
        const next = {
            ...prev,
            tracks,
            durationSec: recomputeDuration({ ...prev, tracks }),
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: {
                type: ADD_CLIP,
                execute: (p) => addClipCommand.execute(p, { clip }),
            },
        };
    },
};
/* ----------------------------- moveClip ----------------------------- */
export const MOVE_CLIP = "clip.move";
export const moveClipSchema = z.object({ clipId: z.string().min(1), newStart: z.number().nonnegative() });
export const moveClipCommand = {
    type: MOVE_CLIP,
    schema: moveClipSchema,
    execute(prev, { clipId, newStart }) {
        const { clip } = findClip(prev, clipId);
        const moved = { ...clip, start: newStart };
        const tracks = prev.tracks.map((t) => t.id === clip.trackId ? { ...t, clips: t.clips.map((c) => (c.id === clipId ? moved : c)) } : t);
        const next = {
            ...prev,
            tracks,
            durationSec: Math.max(recomputeDuration({ ...prev, tracks }), prev.durationSec),
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: {
                type: MOVE_CLIP,
                execute: (p) => moveClipCommand.execute(p, { clipId, newStart: clip.start }),
            },
        };
    },
};
/* ----------------------------- clipAudio ---------------------------- */
export const SET_CLIP_AUDIO = "clip.audio";
export const setClipAudioSchema = z.object({
    clipId: z.string().min(1),
    gainDb: z.number().min(-60).max(0),
    muted: z.boolean(),
});
export const setClipAudioCommand = {
    type: SET_CLIP_AUDIO,
    schema: setClipAudioSchema,
    execute(prev, { clipId, gainDb, muted }) {
        const { clip, track } = findClip(prev, clipId);
        const prior = clip.audio ?? { gainDb: 0, muted: false };
        const updated = { ...clip, audio: { gainDb, muted } };
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
        return {
            next: { ...prev, tracks, updatedAt: new Date().toISOString() },
            inverse: {
                type: SET_CLIP_AUDIO,
                execute: (p) => setClipAudioCommand.execute(p, { clipId, gainDb: prior.gainDb, muted: prior.muted }),
            },
        };
    },
};
/* ---------------------------- clipEffects --------------------------- */
export const SET_CLIP_EFFECTS = "clip.effects";
export const setClipEffectsSchema = z.object({
    clipId: z.string().min(1),
    brightness: z.number().min(-1).max(1),
    contrast: z.number().min(0).max(2),
    saturation: z.number().min(0).max(3),
});
export const setClipEffectsCommand = {
    type: SET_CLIP_EFFECTS,
    schema: setClipEffectsSchema,
    execute(prev, { clipId, brightness, contrast, saturation }) {
        const { clip, track } = findClip(prev, clipId);
        const prior = clip.effects ?? { brightness: 0, contrast: 1, saturation: 1 };
        const updated = { ...clip, effects: { brightness, contrast, saturation } };
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
        return { next: { ...prev, tracks, updatedAt: new Date().toISOString() }, inverse: { type: SET_CLIP_EFFECTS, execute: (p) => setClipEffectsCommand.execute(p, { clipId, ...prior }) } };
    },
};
/* ---------------------------- clipSpeed ----------------------------- */
export const SET_CLIP_SPEED = "clip.speed";
export const setClipSpeedSchema = z.object({ clipId: z.string().min(1), playbackRate: z.number().min(0.25).max(4) });
export const setClipSpeedCommand = {
    type: SET_CLIP_SPEED, schema: setClipSpeedSchema,
    execute(prev, { clipId, playbackRate }) {
        const { clip, track } = findClip(prev, clipId);
        const priorRate = clip.playbackRate ?? 1;
        const duration = clip.duration * priorRate / playbackRate;
        if (clip.transitionIn && clip.transitionIn.duration > duration + 1e-9)
            throw new CommandError("SPEED_CONFLICTS_WITH_TRANSITION");
        const updated = { ...clip, playbackRate, duration };
        const ordered = track.clips.map((c) => c.id === clipId ? updated : c).sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const changedIndex = ordered.findIndex((c) => c.id === clipId);
        for (let i = changedIndex + 1; i < ordered.length; i += 1) {
            const current = ordered[i];
            if (!current.transitionIn)
                break;
            const previous = ordered[i - 1];
            ordered[i] = { ...current, start: previous.start + previous.duration - current.transitionIn.duration };
        }
        const byId = new Map(ordered.map((c) => [c.id, c]));
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => byId.get(c.id) ?? c) } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return { next, inverse: { type: SET_CLIP_SPEED, execute: (p) => setClipSpeedCommand.execute(p, { clipId, playbackRate: priorRate }) } };
    },
};
/* -------------------------- clipTransition ------------------------- */
export const SET_CLIP_TRANSITION = "clip.transition";
export const setClipTransitionSchema = z.object({
    clipId: z.string().min(1),
    mode: z.enum(["none", "crossfade"]),
    duration: z.number().min(0.1).max(2).optional(),
});
function restoreClipTransition(prev, clipId, target) {
    const { clip, track } = findClip(prev, clipId);
    const current = { start: clip.start, transitionIn: clip.transitionIn ?? null };
    const updated = { ...clip, start: target.start, transitionIn: target.transitionIn };
    const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
    const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
    return { next, inverse: { type: SET_CLIP_TRANSITION, execute: (p) => restoreClipTransition(p, clipId, current) } };
}
export const setClipTransitionCommand = {
    type: SET_CLIP_TRANSITION,
    schema: setClipTransitionSchema,
    execute(prev, { clipId, mode, duration }) {
        const { clip, track } = findClip(prev, clipId);
        if (track.kind !== "video")
            throw new CommandError("TRANSITION_REQUIRES_VIDEO_TRACK");
        const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const index = ordered.findIndex((c) => c.id === clipId);
        const previous = index > 0 ? ordered[index - 1] : undefined;
        if (mode === "crossfade") {
            if (!previous)
                throw new CommandError("TRANSITION_REQUIRES_PREVIOUS_CLIP");
            const d = duration ?? 0.5;
            const maxDuration = Math.min(previous.duration, clip.duration, 2);
            if (d > maxDuration + 1e-9)
                throw new CommandError(`TRANSITION_TOO_LONG: ${d} > ${maxDuration}`);
            return restoreClipTransition(prev, clipId, {
                start: previous.start + previous.duration - d,
                transitionIn: { type: "crossfade", duration: d },
            });
        }
        return restoreClipTransition(prev, clipId, {
            start: clip.transitionIn && previous ? previous.start + previous.duration : clip.start,
            transitionIn: null,
        });
    },
};
/* --------------------------- clipTransform -------------------------- */
export const SET_CLIP_TRANSFORM = "clip.transform";
export const setClipTransformSchema = z.object({
    clipId: z.string().min(1),
    scale: z.number().min(0.1).max(4),
    x: z.number().min(-1).max(1),
    y: z.number().min(-1).max(1),
    opacity: z.number().min(0).max(1),
});
export const setClipTransformCommand = {
    type: SET_CLIP_TRANSFORM,
    schema: setClipTransformSchema,
    execute(prev, { clipId, scale, x, y, opacity }) {
        const { clip, track } = findClip(prev, clipId);
        const prior = clip.transform ?? { scale: 1, x: 0, y: 0, opacity: 1 };
        const updated = { ...clip, transform: { scale, x, y, opacity } };
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
        return {
            next: { ...prev, tracks, updatedAt: new Date().toISOString() },
            inverse: {
                type: SET_CLIP_TRANSFORM,
                execute: (p) => setClipTransformCommand.execute(p, { clipId, ...prior }),
            },
        };
    },
};
/* --------------------------- ripple editing ------------------------- */
export const RIPPLE_DELETE_CLIPS = "clip.rippleDelete";
export const rippleDeleteClipsSchema = z.object({ clipIds: z.array(z.string().min(1)).min(1) });
export const RIPPLE_TRIM_CLIP = "clip.rippleTrim";
export const rippleTrimClipSchema = z.object({
    clipId: z.string().min(1),
    newInPoint: z.number().nonnegative().optional(),
    newSourceEnd: z.number().nonnegative().optional(),
});
function restoreRippleSnapshot(prev, snapshots) {
    const wanted = new Map(snapshots.map((s) => [s.trackId, s.clips]));
    const current = prev.tracks.filter((t) => wanted.has(t.id)).map((t) => ({ trackId: t.id, clips: t.clips }));
    const tracks = prev.tracks.map((t) => wanted.has(t.id) ? { ...t, clips: wanted.get(t.id) } : t);
    const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
    return { next, inverse: { type: "clip.rippleRestore", execute: (p) => restoreRippleSnapshot(p, current) } };
}
function mergeIntervals(intervals) {
    const ordered = [...intervals].sort((a, b) => a.start - b.start || a.end - b.end);
    const merged = [];
    for (const interval of ordered) {
        const last = merged[merged.length - 1];
        if (last && interval.start <= last.end + 1e-9)
            last.end = Math.max(last.end, interval.end);
        else
            merged.push({ ...interval });
    }
    return merged;
}
export const rippleDeleteClipsCommand = {
    type: RIPPLE_DELETE_CLIPS,
    schema: rippleDeleteClipsSchema,
    execute(prev, { clipIds }) {
        if (new Set(clipIds).size !== clipIds.length)
            throw new CommandError("RIPPLE_DUPLICATE_CLIP_ID");
        const selected = new Set(clipIds);
        for (const id of clipIds)
            findClip(prev, id);
        const affected = prev.tracks.filter((t) => t.clips.some((c) => selected.has(c.id)));
        const snapshots = affected.map((t) => ({ trackId: t.id, clips: t.clips }));
        const replacements = new Map();
        for (const track of affected) {
            const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
            for (let i = 0; i < ordered.length; i += 1) {
                if (!selected.has(ordered[i].id))
                    continue;
                const prevClip = ordered[i - 1];
                const nextClip = ordered[i + 1];
                if (ordered[i].transitionIn && prevClip && !selected.has(prevClip.id))
                    throw new CommandError("RIPPLE_TRANSITION_CONFLICT");
                if (nextClip?.transitionIn && !selected.has(nextClip.id))
                    throw new CommandError("RIPPLE_TRANSITION_CONFLICT");
            }
            const intervals = mergeIntervals(ordered.filter((c) => selected.has(c.id)).map((c) => ({ start: c.start, end: c.start + c.duration })));
            const remaining = ordered.filter((c) => !selected.has(c.id)).map((clip) => {
                for (const interval of intervals) {
                    if (clip.start < interval.end - 1e-9 && clip.start + clip.duration > interval.start + 1e-9)
                        throw new CommandError("RIPPLE_OVERLAP_CONFLICT");
                }
                const shift = intervals.filter((x) => x.end <= clip.start + 1e-9).reduce((sum, x) => sum + x.end - x.start, 0);
                return shift > 0 ? { ...clip, start: Math.max(0, clip.start - shift) } : clip;
            });
            replacements.set(track.id, remaining);
        }
        const tracks = prev.tracks.map((t) => replacements.has(t.id) ? { ...t, clips: replacements.get(t.id) } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return { next, inverse: { type: "clip.rippleRestore", execute: (p) => restoreRippleSnapshot(p, snapshots) } };
    },
};
export const rippleTrimClipCommand = {
    type: RIPPLE_TRIM_CLIP,
    schema: rippleTrimClipSchema,
    execute(prev, { clipId, newInPoint, newSourceEnd }) {
        if (newInPoint === undefined && newSourceEnd === undefined)
            throw new CommandError("INVALID_RIPPLE_TRIM");
        const { clip, track } = findClip(prev, clipId);
        const asset = findAsset(prev, clip.assetId);
        const rate = clip.playbackRate ?? 1;
        const sourceEnd = clip.inPoint + clip.duration * rate;
        let updated;
        if (newSourceEnd !== undefined) {
            const sourceSpan = newSourceEnd - clip.inPoint;
            if (sourceSpan <= 0)
                throw new CommandError("INVALID_RIPPLE_TRIM");
            updated = { ...clip, duration: sourceSpan / rate };
        }
        else {
            const nip = newInPoint;
            const sourceSpan = sourceEnd - nip;
            if (sourceSpan <= 0)
                throw new CommandError("INVALID_RIPPLE_TRIM");
            updated = { ...clip, inPoint: nip, duration: sourceSpan / rate };
        }
        const bad = validateClipAgainstAsset(updated, asset);
        if (bad)
            throw new CommandError(`INVALID_RIPPLE_TRIM: ${bad}`);
        if (updated.transitionIn && updated.transitionIn.duration > updated.duration + 1e-9)
            throw new CommandError("RIPPLE_TRIM_TRANSITION_CONFLICT");
        const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const index = ordered.findIndex((c) => c.id === clipId);
        const nextClip = ordered[index + 1];
        if (nextClip?.transitionIn && nextClip.transitionIn.duration > updated.duration + 1e-9)
            throw new CommandError("RIPPLE_TRIM_TRANSITION_CONFLICT");
        const delta = updated.duration - clip.duration;
        const changed = ordered.map((c, i) => i === index ? updated : i > index ? { ...c, start: c.start + delta } : c);
        if (changed.some((c) => c.start < -1e-9))
            throw new CommandError("RIPPLE_TRIM_NEGATIVE_START");
        const byId = new Map(changed.map((c) => [c.id, { ...c, start: Math.max(0, c.start) }]));
        const snapshots = [{ trackId: track.id, clips: track.clips }];
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => byId.get(c.id) ?? c) } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return { next, inverse: { type: "clip.rippleRestore", execute: (p) => restoreRippleSnapshot(p, snapshots) } };
    },
};
/* ----------------------------- trimClip ----------------------------- */
export const TRIM_CLIP = "clip.trim";
export const trimClipSchema = z.object({
    clipId: z.string().min(1),
    /** New in-point (trim left). */
    newInPoint: z.number().nonnegative().optional(),
    /** New source end (trim right). */
    newSourceEnd: z.number().nonnegative().optional(),
});
export const trimClipCommand = {
    type: TRIM_CLIP,
    schema: trimClipSchema,
    execute(prev, { clipId, newInPoint, newSourceEnd }) {
        if (newInPoint === undefined && newSourceEnd === undefined) {
            throw new CommandError("INVALID_TRIM: provide newInPoint or newSourceEnd");
        }
        const { clip, track } = findClip(prev, clipId);
        const asset = findAsset(prev, clip.assetId);
        const rate = clip.playbackRate ?? 1;
        const originalSourceEnd = clip.inPoint + clip.duration * rate;
        let updated = clip;
        if (newSourceEnd !== undefined) {
            const sourceSpan = newSourceEnd - clip.inPoint;
            const duration = sourceSpan / rate;
            if (duration <= 0)
                throw new CommandError(`INVALID_TRIM: duration ${duration}`);
            updated = { ...clip, duration };
        }
        else {
            const nip = newInPoint;
            const duration = (originalSourceEnd - nip) / rate;
            if (duration <= 0)
                throw new CommandError(`INVALID_TRIM: duration ${duration}`);
            updated = { ...clip, inPoint: nip, duration };
        }
        const bad = validateClipAgainstAsset(updated, asset);
        if (bad)
            throw new CommandError(`INVALID_TRIM: ${bad}`);
        if (updated.transitionIn && updated.transitionIn.duration > updated.duration + 1e-9)
            throw new CommandError("TRIM_TRANSITION_CONFLICT");
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => (c.id === clipId ? updated : c)) } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return {
            next,
            inverse: {
                type: TRIM_CLIP,
                execute: (p) => trimClipCommand.execute(p, newSourceEnd !== undefined
                    ? { clipId, newSourceEnd: originalSourceEnd }
                    : { clipId, newInPoint: clip.inPoint }),
            },
        };
    },
};
/* ----------------------------- placeCaption ------------------------- */
export const PLACE_CAPTION = "caption.place";
export const placeCaptionSchema = z.object({
    text: z.string().min(1),
    start: z.number().nonnegative().default(0),
    duration: z.number().positive().default(3),
});
export const placeCaptionCommand = {
    type: PLACE_CAPTION,
    schema: placeCaptionSchema,
    execute(prev, { text, start, duration }) {
        const existing = prev.tracks.find((t) => t.kind === "text");
        const trackId = existing?.id ?? "text-captions";
        const used = new Set(prev.tracks.flatMap((t) => t.captions.map((c) => c.id)));
        let n = 1;
        while (used.has(`cap-${n}`))
            n += 1;
        const caption = {
            id: `cap-${n}`, text, start, duration, trackId,
            style: { x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.6 },
        };
        const tracks = existing
            ? prev.tracks.map((t) => t.id === trackId ? { ...t, captions: [...t.captions, caption] } : t)
            : [...prev.tracks, { id: trackId, kind: "text", clips: [], captions: [caption] }];
        const next = {
            ...prev, tracks,
            durationSec: Math.max(prev.durationSec, start + duration),
            updatedAt: new Date().toISOString(),
        };
        const inverse = {
            type: "caption.unplace",
            execute(p) {
                const track = p.tracks.find((t) => t.id === trackId);
                if (!track)
                    throw new CommandError(`CAPTION_TRACK_NOT_FOUND: ${trackId}`);
                const remaining = track.captions.filter((c) => c.id !== caption.id);
                const nextTracks = !existing && remaining.length === 0
                    ? p.tracks.filter((t) => t.id !== trackId)
                    : p.tracks.map((t) => t.id === trackId ? { ...t, captions: remaining } : t);
                return { next: { ...p, tracks: nextTracks, updatedAt: new Date().toISOString() }, inverse: placeCaptionCommand };
            },
        };
        return { next, inverse, result: { captionId: caption.id, trackId } };
    },
};
/* ----------------------------- captionAdd --------------------------- */
export const ADD_CAPTION = "caption.add";
export const addCaptionSchema = z.object({
    caption: captionSchema,
});
export const addCaptionCommand = {
    type: ADD_CAPTION,
    schema: addCaptionSchema,
    execute(prev, { caption }) {
        if (prev.tracks.some((t) => t.captions.some((c) => c.id === caption.id))) {
            throw new CommandError(`CAPTION_DUPLICATE: ${caption.id}`);
        }
        const tracks = prev.tracks.map((t) => t.id === caption.trackId ? { ...t, captions: [...t.captions, caption] } : t);
        const next = {
            ...prev,
            tracks,
            durationSec: Math.max(recomputeDuration({ ...prev, tracks }), caption.start + caption.duration, prev.durationSec),
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: {
                type: "caption.remove",
                execute: (p) => removeCaptionCommand.execute(p, { captionId: caption.id, trackId: caption.trackId }),
            },
        };
    },
};
export const REMOVE_CAPTION = "caption.remove";
export const removeCaptionCommand = {
    type: REMOVE_CAPTION,
    execute(prev, { captionId, trackId }) {
        const track = prev.tracks.find((t) => t.id === trackId);
        const caption = track?.captions.find((c) => c.id === captionId);
        if (!caption)
            throw new CommandError(`CAPTION_NOT_FOUND: ${captionId}`);
        const tracks = prev.tracks.map((t) => t.id === trackId ? { ...t, captions: t.captions.filter((c) => c.id !== captionId) } : t);
        const next = { ...prev, tracks, updatedAt: new Date().toISOString() };
        return {
            next,
            inverse: {
                type: ADD_CAPTION,
                execute: (p) => addCaptionCommand.execute(p, { caption }),
            },
        };
    },
};
/* ----------------------------- changeAspect -------------------------- */
export const CHANGE_ASPECT = "project.changeAspect";
export const changeAspectSchema = z.object({ ratio: exportResolutionSchema });
export const changeAspectCommand = {
    type: CHANGE_ASPECT,
    schema: changeAspectSchema,
    execute(prev, { ratio }) {
        if (prev.aspectRatio === ratio) {
            return { next: prev, inverse: changeAspectCommand };
        }
        const prior = prev.aspectRatio;
        const next = { ...prev, aspectRatio: ratio, updatedAt: new Date().toISOString() };
        return {
            next,
            inverse: {
                type: CHANGE_ASPECT,
                execute: (p) => changeAspectCommand.execute(p, { ratio: prior }),
            },
        };
    },
};
/* ----------------------------- addTrack ----------------------------- */
// Media-kind tracks (video/audio) are SINGLETONS: the timeline permits at most
// one video track and one audio track. Text/caption tracks may be multiple.
// This invariant lets PLACE_PROBED_MEDIA reuse the existing track instead of
// racing to create a duplicate (ROOT_CAUSE_1).
export const ADD_TRACK = "track.add";
export const addTrackSchema = z.object({
    track: z.object({
        id: z.string().min(1),
        kind: z.enum(["video", "audio", "text"]),
        clips: z.array(clipSchema).default([]),
        captions: z.array(captionSchema).default([]),
    }),
});
export const addTrackCommand = {
    type: ADD_TRACK,
    schema: addTrackSchema,
    execute(prev, { track }) {
        if (track.kind !== "text" && prev.tracks.some((t) => t.kind === track.kind)) {
            throw new CommandError(`TRACK_DUPLICATE_KIND: ${track.kind}`);
        }
        if (prev.tracks.some((t) => t.id === track.id)) {
            throw new CommandError(`TRACK_DUPLICATE_ID: ${track.id}`);
        }
        const next = {
            ...prev,
            tracks: [...prev.tracks, track],
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: {
                type: REMOVE_TRACK,
                execute: (p) => removeTrackCommand.execute(p, { trackId: track.id }),
            },
        };
    },
};
export const REMOVE_TRACK = "track.remove";
export const removeTrackCommand = {
    type: REMOVE_TRACK,
    execute(prev, { trackId }) {
        const track = prev.tracks.find((t) => t.id === trackId);
        if (!track)
            throw new CommandError(`TRACK_NOT_FOUND: ${trackId}`);
        const next = {
            ...prev,
            tracks: prev.tracks.filter((t) => t.id !== trackId),
            durationSec: recomputeDuration({ ...prev, tracks: prev.tracks.filter((t) => t.id !== trackId) }),
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: { type: ADD_TRACK, execute: (p) => addTrackCommand.execute(p, { track }) },
        };
    },
};
/* ----------------------------- placeProbedMedia --------------------- */
// Atomic import+place. A single CommandBus operation that:
//   1. validates the probe (must be a successful probe)
//   2. builds the immutable MediaAsset
//   3. ensures a suitable (singleton) track exists for its kind
//   4. calculates insertion position from CURRENT state
//   5. creates the Clip
//   6. updates duration
//   7. returns the created clipId so the UI can select it
// This removes the RC1 race where the MediaPanel read a stale `project`
// snapshot, found no track, and silently skipped clip placement.
const placeProbeSchema = z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    sourcePath: z.string().min(1),
    kind: z.enum(["video", "audio", "image", "unknown"]),
    durationSec: z.number().positive(),
    width: z.number().int().nonnegative().optional(),
    height: z.number().int().nonnegative().optional(),
    fps: z.number().positive().optional(),
    hasAudio: z.boolean(),
    videoCodec: z.string().nullable().optional(),
    audioCodec: z.string().nullable().optional(),
    probeStatus: z.string(),
});
export const PLACE_PROBED_MEDIA = "media.placeProbed";
export const placeProbedMediaSchema = z.object({
    probe: placeProbeSchema,
    place: z.boolean().default(true),
});
export const placeProbedMediaCommand = {
    type: PLACE_PROBED_MEDIA,
    schema: placeProbedMediaSchema,
    execute(prev, { probe, place }) {
        if (probe.probeStatus !== "ok") {
            throw new CommandError(`PROBE_NOT_OK: ${probe.probeStatus}`);
        }
        if (prev.assets.some((a) => a.id === probe.id)) {
            throw new CommandError(`ASSET_DUPLICATE: ${probe.id}`);
        }
        const assetKind = probe.kind === "audio" ? "audio" : probe.kind === "video" ? "video" : "image";
        const trackKind = assetKind === "audio" ? "audio" : "video";
        const asset = {
            id: probe.id,
            name: probe.name,
            sourcePath: probe.sourcePath,
            kind: assetKind,
            durationSec: probe.durationSec,
            width: probe.width || undefined,
            height: probe.height || undefined,
            fps: probe.fps || undefined,
            hasAudio: probe.hasAudio,
            createdAt: new Date().toISOString(),
        };
        const newTrackId = `${trackKind}-${probe.id}`;
        const existing = prev.tracks.find((t) => t.kind === trackKind);
        let tracks = prev.tracks;
        let targetTrackId;
        if (existing) {
            targetTrackId = existing.id;
        }
        else {
            tracks = [...tracks, { id: newTrackId, kind: trackKind, clips: [], captions: [] }];
            targetTrackId = newTrackId;
        }
        let next = {
            ...prev,
            assets: [...prev.assets, asset],
            tracks,
            updatedAt: new Date().toISOString(),
        };
        let clipId;
        if (place) {
            const track = next.tracks.find((t) => t.id === targetTrackId);
            const start = Math.max(0, ...track.clips.map((c) => c.start + c.duration));
            clipId = `${probe.id}-clip`;
            const clip = {
                id: clipId,
                assetId: asset.id,
                inPoint: 0,
                duration: asset.durationSec,
                start,
                trackId: targetTrackId,
                transform: { scale: 1, x: 0, y: 0, opacity: 1 },
                audio: { gainDb: 0, muted: false },
                effects: { brightness: 0, contrast: 1, saturation: 1 },
                playbackRate: 1,
                transitionIn: null,
            };
            next = {
                ...next,
                tracks: next.tracks.map((t) => (t.id === targetTrackId ? { ...t, clips: [...t.clips, clip] } : t)),
            };
            next = { ...next, durationSec: Math.max(recomputeDuration(next), next.durationSec) };
        }
        const inverse = {
            type: "media.unplaceProbed",
            execute(p, { probe: pr, place: pl }) {
                const ak = pr.kind === "audio" ? "audio" : "video";
                let r = { ...p, assets: p.assets.filter((a) => a.id !== pr.id) };
                if (p.tracks.some((t) => t.id === `${ak}-${pr.id}`)) {
                    r = { ...r, tracks: r.tracks.filter((t) => t.id !== `${ak}-${pr.id}`) };
                }
                else if (pl) {
                    r = {
                        ...r,
                        tracks: r.tracks.map((t) => t.kind === ak ? { ...t, clips: t.clips.filter((c) => c.id !== `${pr.id}-clip`) } : t),
                    };
                }
                r = { ...r, durationSec: recomputeDuration(r) };
                return { next: r, inverse: placeProbedMediaCommand };
            },
        };
        return { next, inverse, result: { clipId } };
    },
};
/* ---------------------- insert / overwrite edit --------------------- */
export const TIMELINE_INSERT_ASSET = "timeline.insertAsset";
export const TIMELINE_OVERWRITE_ASSET = "timeline.overwriteAsset";
export const timelineAssetEditSchema = z.object({
    assetId: z.string().min(1),
    clipId: z.string().min(1),
    atSec: z.number().nonnegative(),
});
function restoreTimelineEditSnapshot(prev, snapshot) {
    const current = prev;
    return {
        next: snapshot,
        inverse: { type: "timeline.restore", execute: (p) => restoreTimelineEditSnapshot(p, current) },
    };
}
function timelineTrackKind(asset) {
    return asset.kind === "audio" ? "audio" : "video";
}
function makeTimelineEditClip(asset, trackId, clipId, atSec) {
    return {
        id: clipId, assetId: asset.id, inPoint: 0, duration: asset.durationSec, start: atSec, trackId,
        transform: { scale: 1, x: 0, y: 0, opacity: 1 },
        audio: { gainDb: 0, muted: false },
        effects: { brightness: 0, contrast: 1, saturation: 1 },
        playbackRate: 1, transitionIn: null,
    };
}
function assertTimelineClipIdAvailable(project, clipId) {
    if (project.tracks.some((t) => t.clips.some((c) => c.id === clipId))) {
        throw new CommandError(`TIMELINE_CLIP_ID_DUPLICATE: ${clipId}`);
    }
}
function ensureTimelineTrack(project, asset) {
    const kind = timelineTrackKind(asset);
    const existing = project.tracks.find((t) => t.kind === kind);
    if (existing)
        return { tracks: project.tracks, track: existing };
    const id = `timeline-${kind}`;
    if (project.tracks.some((t) => t.id === id))
        throw new CommandError(`TIMELINE_TRACK_ID_CONFLICT: ${id}`);
    const track = { id, kind, clips: [], captions: [] };
    return { tracks: [...project.tracks, track], track };
}
export const timelineInsertAssetCommand = {
    type: TIMELINE_INSERT_ASSET,
    schema: timelineAssetEditSchema,
    execute(prev, { assetId, clipId, atSec }) {
        const asset = findAsset(prev, assetId);
        assertTimelineClipIdAvailable(prev, clipId);
        const ensured = ensureTimelineTrack(prev, asset);
        const ordered = [...ensured.track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const covering = ordered.filter((c) => c.start < atSec - 1e-9 && c.start + c.duration > atSec + 1e-9);
        if (covering.length > 1)
            throw new CommandError("TIMELINE_OVERLAP_CONFLICT");
        const nextAtBoundary = ordered.find((c) => c.start >= atSec - 1e-9);
        if (covering[0]?.transitionIn || nextAtBoundary?.transitionIn)
            throw new CommandError("TIMELINE_TRANSITION_CONFLICT");
        const inserted = makeTimelineEditClip(asset, ensured.track.id, clipId, atSec);
        const badInserted = validateClipAgainstAsset(inserted, asset);
        if (badInserted)
            throw new CommandError(`INVALID_TIMELINE_EDIT: ${badInserted}`);
        const split = covering[0];
        const replacement = [];
        for (const c of ordered) {
            if (split && c.id === split.id) {
                const leftDuration = atSec - c.start;
                const rightDuration = c.start + c.duration - atSec;
                const rate = c.playbackRate ?? 1;
                const rightId = `${c.id}__insert_r_${clipId}`;
                assertTimelineClipIdAvailable(prev, rightId);
                const right = {
                    ...c, id: rightId, start: atSec + asset.durationSec,
                    inPoint: c.inPoint + leftDuration * rate, duration: rightDuration,
                };
                const left = { ...c, duration: leftDuration };
                if (validateClipAgainstAsset(left, findAsset(prev, left.assetId)) || validateClipAgainstAsset(right, findAsset(prev, right.assetId))) {
                    throw new CommandError("INVALID_TIMELINE_INSERT_SPLIT");
                }
                replacement.push(left, right);
            }
            else if (c.start >= atSec - 1e-9)
                replacement.push({ ...c, start: c.start + asset.durationSec });
            else
                replacement.push(c);
        }
        replacement.push(inserted);
        replacement.sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const tracks = ensured.tracks.map((t) => t.id === ensured.track.id ? { ...t, clips: replacement } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return { next, inverse: { type: "timeline.restore", execute: (p) => restoreTimelineEditSnapshot(p, prev) } };
    },
};
export const timelineOverwriteAssetCommand = {
    type: TIMELINE_OVERWRITE_ASSET,
    schema: timelineAssetEditSchema,
    execute(prev, { assetId, clipId, atSec }) {
        const asset = findAsset(prev, assetId);
        assertTimelineClipIdAvailable(prev, clipId);
        const ensured = ensureTimelineTrack(prev, asset);
        const ordered = [...ensured.track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const endSec = atSec + asset.durationSec;
        for (let i = 1; i < ordered.length; i += 1) {
            const a = ordered[i - 1], b = ordered[i];
            if (b.start < a.start + a.duration - 1e-9 && b.start < endSec - 1e-9 && a.start + a.duration > atSec + 1e-9) {
                throw new CommandError("TIMELINE_OVERLAP_CONFLICT");
            }
        }
        const transitionConflict = ordered.some((c) => c.transitionIn && c.start <= endSec + 1e-9 && c.start + c.duration >= atSec - 1e-9);
        if (transitionConflict)
            throw new CommandError("TIMELINE_TRANSITION_CONFLICT");
        const inserted = makeTimelineEditClip(asset, ensured.track.id, clipId, atSec);
        const replacement = [];
        for (const c of ordered) {
            const clipEnd = c.start + c.duration;
            if (clipEnd <= atSec + 1e-9 || c.start >= endSec - 1e-9) {
                replacement.push(c);
                continue;
            }
            const keepLeft = c.start < atSec - 1e-9;
            const keepRight = clipEnd > endSec + 1e-9;
            const rate = c.playbackRate ?? 1;
            if (keepLeft)
                replacement.push({ ...c, duration: atSec - c.start });
            if (keepRight) {
                const rightId = keepLeft ? `${c.id}__overwrite_r_${clipId}` : c.id;
                if (keepLeft)
                    assertTimelineClipIdAvailable(prev, rightId);
                const right = {
                    ...c,
                    id: rightId,
                    start: endSec,
                    inPoint: c.inPoint + (endSec - c.start) * rate,
                    duration: clipEnd - endSec,
                };
                if (validateClipAgainstAsset(right, findAsset(prev, right.assetId)))
                    throw new CommandError("INVALID_TIMELINE_OVERWRITE_SPLIT");
                replacement.push(right);
            }
        }
        replacement.push(inserted);
        replacement.sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
        const tracks = ensured.tracks.map((t) => t.id === ensured.track.id ? { ...t, clips: replacement } : t);
        const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
        return { next, inverse: { type: "timeline.restore", execute: (p) => restoreTimelineEditSnapshot(p, prev) } };
    },
};
/* ----------------------------- relinkMedia -------------------------- */
export const RELINK_MEDIA = "media.relink";
export const relinkMediaSchema = z.object({
    assetId: z.string().min(1),
    probe: z.object({
        name: z.string().min(1),
        sourcePath: z.string().min(1),
        kind: z.enum(["video", "audio", "image", "unknown"]),
        durationSec: z.number().positive(),
        width: z.number().int().nonnegative().optional(),
        height: z.number().int().nonnegative().optional(),
        fps: z.number().positive().optional(),
        hasAudio: z.boolean(),
        videoCodec: z.string().nullable().optional(),
        audioCodec: z.string().nullable().optional(),
        probeStatus: z.string(),
    }),
});
export const relinkMediaCommand = {
    type: RELINK_MEDIA,
    schema: relinkMediaSchema,
    execute(prev, { assetId, probe }) {
        if (probe.probeStatus !== "ok")
            throw new CommandError(`RELINK_PROBE_NOT_OK: ${probe.probeStatus}`);
        const prior = findAsset(prev, assetId);
        const nextKind = probe.kind === "audio" ? "audio" : probe.kind === "video" ? "video" : "image";
        if (nextKind !== prior.kind)
            throw new CommandError(`RELINK_KIND_MISMATCH: ${prior.kind} -> ${nextKind}`);
        const replacement = {
            ...prior,
            name: probe.name,
            sourcePath: probe.sourcePath,
            durationSec: probe.durationSec,
            width: probe.width || undefined,
            height: probe.height || undefined,
            fps: probe.fps || undefined,
            hasAudio: probe.hasAudio,
            checksum: undefined,
        };
        for (const track of prev.tracks) {
            for (const clip of track.clips.filter((c) => c.assetId === assetId)) {
                const bad = validateClipAgainstAsset(clip, replacement);
                if (bad)
                    throw new CommandError(`RELINK_INCOMPATIBLE_CLIP: ${clip.id}: ${bad}`);
            }
        }
        const next = { ...prev, assets: prev.assets.map((a) => a.id === assetId ? replacement : a), updatedAt: new Date().toISOString() };
        const inverse = {
            type: "media.relink.restore",
            execute(p) {
                return {
                    next: { ...p, assets: p.assets.map((a) => a.id === assetId ? prior : a), updatedAt: new Date().toISOString() },
                    inverse: relinkMediaCommand,
                };
            },
        };
        return { next, inverse };
    },
};
/* ----------------------------- splitClip ---------------------------- */
export const SPLIT_CLIP = "clip.split";
export const splitClipSchema = z.object({ clipId: z.string().min(1), t: z.number().positive() });
export const splitClipCommand = {
    type: SPLIT_CLIP,
    schema: splitClipSchema,
    execute(prev, { clipId, t }) {
        const { clip, track } = findClip(prev, clipId);
        if (!(t > 0 && t < clip.duration)) {
            throw new CommandError(`INVALID_SPLIT_POINT: t=${t} must satisfy 0 < t < ${clip.duration}`);
        }
        const left = { ...clip, duration: t };
        const right = {
            ...clip,
            id: `${clip.id}__r`,
            inPoint: clip.inPoint + t,
            start: clip.start + t,
            duration: clip.duration - t,
        };
        const newClips = track.clips.flatMap((c) => (c.id === clipId ? [left, right] : [c]));
        const tracks = prev.tracks.map((tr) => (tr.id === track.id ? { ...tr, clips: newClips } : tr));
        const next = {
            ...prev,
            tracks,
            durationSec: recomputeDuration({ ...prev, tracks }),
            updatedAt: new Date().toISOString(),
        };
        return {
            next,
            inverse: {
                type: "clip.merge",
                execute: (p) => {
                    const merged = { ...left, duration: clip.duration };
                    const mergedTracks = p.tracks.map((tr) => tr.id === track.id
                        ? { ...tr, clips: tr.clips.filter((c) => c.id !== right.id).map((c) => (c.id === left.id ? merged : c)) }
                        : tr);
                    return {
                        next: { ...p, tracks: mergedTracks, updatedAt: new Date().toISOString() },
                        inverse: splitClipCommand,
                    };
                },
            },
        };
    },
};
//# sourceMappingURL=commands.js.map