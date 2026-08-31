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
        let updated = clip;
        if (newSourceEnd !== undefined) {
            const duration = newSourceEnd - clip.inPoint;
            if (duration <= 0)
                throw new CommandError(`INVALID_TRIM: duration ${duration}`);
            updated = { ...clip, duration };
        }
        else {
            const nip = newInPoint;
            const duration = clip.inPoint + clip.duration - nip;
            if (duration <= 0)
                throw new CommandError(`INVALID_TRIM: duration ${duration}`);
            updated = { ...clip, inPoint: nip, duration };
        }
        const bad = validateClipAgainstAsset(updated, asset);
        if (bad)
            throw new CommandError(`INVALID_TRIM: ${bad}`);
        const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => (c.id === clipId ? updated : c)) } : t);
        const next = { ...prev, tracks, updatedAt: new Date().toISOString() };
        return {
            next,
            inverse: {
                type: TRIM_CLIP,
                execute: (p) => trimClipCommand.execute(p, { clipId, newInPoint: clip.inPoint }),
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