import { z } from "zod";
import {
  type Project,
  type Clip,
  type MediaAsset,
  type Track,
  exportResolutionSchema,
  captionSchema,
  clipSchema,
  validateClipAgainstAsset,
} from "@haios/project-model";
import { EditCommand, CommandError } from "./types.js";

function findClip(project: Project, clipId: string): { clip: Clip; track: Track } {
  for (const track of project.tracks) {
    const clip = track.clips.find((c) => c.id === clipId);
    if (clip) return { clip, track };
  }
  throw new CommandError(`CLIP_NOT_FOUND: ${clipId}`);
}

function findAsset(project: Project, assetId: string): MediaAsset {
  const a = project.assets.find((x) => x.id === assetId);
  if (!a) throw new CommandError(`ASSET_NOT_FOUND: ${assetId}`);
  return a;
}

function findTrack(project: Project, trackId: string): Track {
  const track = project.tracks.find((candidate) => candidate.id === trackId);
  if (!track) throw new CommandError(`TRACK_NOT_FOUND: ${trackId}`);
  return track;
}

function assertTrackUnlocked(track: Track): void {
  if (track.locked) throw new CommandError(`TRACK_LOCKED: ${track.id}`);
}

function recomputeDuration(project: Project): number {
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
export const addAssetCommand: EditCommand<{ asset: MediaAsset }> = {
  type: ADD_ASSET,
  execute(prev, { asset }) {
    if (prev.assets.some((a) => a.id === asset.id)) {
      throw new CommandError(`ASSET_DUPLICATE: ${asset.id}`);
    }
    const next: Project = {
      ...prev,
      assets: [...prev.assets, asset],
      updatedAt: new Date().toISOString(),
    };
    return { next, inverse: removeAssetCommand };
  },
};
export const removeAssetCommand: EditCommand<{ asset: MediaAsset }> = {
  type: "asset.remove",
  execute(prev, { asset }) {
    const next: Project = {
      ...prev,
      assets: prev.assets.filter((a) => a.id !== asset.id),
      updatedAt: new Date().toISOString(),
    };
    return { next, inverse: addAssetCommand };
  },
};

/* ----------------------------- addClip ------------------------------ */
export const ADD_CLIP = "clip.add";
export const addClipCommand: EditCommand<{ clip: Clip }> = {
  type: ADD_CLIP,
  execute(prev, { clip }) {
    const targetTrack = findTrack(prev, clip.trackId);
    assertTrackUnlocked(targetTrack);
    const asset = findAsset(prev, clip.assetId);
    const bad = validateClipAgainstAsset(clip, asset);
    if (bad) throw new CommandError(`INVALID_CLIP: ${bad}`);
    const tracks = prev.tracks.map((t) =>
      t.id === clip.trackId ? { ...t, clips: [...t.clips, clip] } : t,
    );
    const next: Project = {
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
export const deleteClipCommand: EditCommand<{ clipId: string }> = {
  type: DELETE_CLIP,
  execute(prev, { clipId }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const tracks = prev.tracks.map((t) =>
      t.id === clip.trackId
        ? { ...t, clips: t.clips.filter((c) => c.id !== clipId) }
        : t,
    );
    const next: Project = {
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
export const moveClipCommand: EditCommand<z.infer<typeof moveClipSchema>> = {
  type: MOVE_CLIP,
  schema: moveClipSchema,
  execute(prev, { clipId, newStart }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const moved: Clip = { ...clip, start: newStart };
    const tracks = prev.tracks.map((t) =>
      t.id === clip.trackId ? { ...t, clips: t.clips.map((c) => (c.id === clipId ? moved : c)) } : t,
    );
    const next: Project = {
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

/* ----------------------- moveAcrossTracks -------------------------- */
/**
 * Atomic cross-track movement authority. This intentionally does not extend
 * `clip.move`: group topology must be validated as a whole before any clip is
 * reassigned, which the general CommandBus batch preflight cannot guarantee.
 */
export const MOVE_CLIP_ACROSS_TRACKS = "clip.moveAcrossTracks";
export const moveAcrossTracksSchema = z.object({
  moves: z.array(z.object({
    clipId: z.string().min(1),
    sourceTrackId: z.string().min(1),
    targetTrackId: z.string().min(1),
    newStart: z.number().nonnegative(),
  })).min(1),
});
type CrossTrackMove = z.infer<typeof moveAcrossTracksSchema>["moves"][number];
type CrossTrackSnapshot = Pick<Project, "tracks" | "durationSec">;

function compareUnicodeCodePoints(a: string, b: string): number {
  const left = Array.from(a, (char) => char.codePointAt(0)!);
  const right = Array.from(b, (char) => char.codePointAt(0)!);
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return left.length - right.length;
}

function transitionPredecessors(project: Project): Map<string, string> {
  const predecessors = new Map<string, string>();
  for (const track of project.tracks) {
    const ordered = [...track.clips].sort((a, b) => a.start - b.start || compareUnicodeCodePoints(a.id, b.id));
    for (let index = 0; index < ordered.length; index += 1) {
      const current = ordered[index];
      if (!current.transitionIn) continue;
      const previous = ordered[index - 1];
      if (!previous) throw new CommandError("CROSS_TRACK_TRANSITION_CONFLICT");
      predecessors.set(current.id, previous.id);
    }
  }
  return predecessors;
}

function assertTransitionTopology(before: Project, after: Project, selectedIds: Set<string>): void {
  const beforePredecessors = transitionPredecessors(before);
  for (const [clipId, predecessorId] of beforePredecessors) {
    if (selectedIds.has(clipId) !== selectedIds.has(predecessorId)) {
      throw new CommandError("CROSS_TRACK_TRANSITION_CONFLICT");
    }
  }
  const afterPredecessors = transitionPredecessors(after);
  const afterClips = new Map(after.tracks.flatMap((track) => track.clips).map((clip) => [clip.id, clip]));
  for (const [clipId, predecessorId] of beforePredecessors) {
    if (afterPredecessors.get(clipId) !== predecessorId) {
      throw new CommandError("CROSS_TRACK_TRANSITION_CONFLICT");
    }
    const clip = afterClips.get(clipId);
    const predecessor = afterClips.get(predecessorId);
    if (!clip || !predecessor || !clip.transitionIn || Math.abs(clip.start - (predecessor.start + predecessor.duration - clip.transitionIn.duration)) > 1e-9) {
      throw new CommandError("CROSS_TRACK_TRANSITION_CONFLICT");
    }
  }
}

function restoreCrossTrackSnapshot(prev: Project, snapshot: CrossTrackSnapshot): { next: Project; inverse: EditCommand } {
  const current: CrossTrackSnapshot = { tracks: prev.tracks, durationSec: prev.durationSec };
  return {
    next: { ...prev, tracks: snapshot.tracks, durationSec: snapshot.durationSec, updatedAt: new Date().toISOString() },
    inverse: { type: MOVE_CLIP_ACROSS_TRACKS, execute: (project) => restoreCrossTrackSnapshot(project, current) },
  };
}

export const moveAcrossTracksCommand: EditCommand<z.infer<typeof moveAcrossTracksSchema>> = {
  type: MOVE_CLIP_ACROSS_TRACKS,
  schema: moveAcrossTracksSchema,
  execute(prev, { moves }) {
    const selectedIds = new Set<string>();
    const resolved: Array<CrossTrackMove & { clip: Clip; source: Track; target: Track }> = [];
    const trackIdCounts = new Map<string, number>();
    for (const track of prev.tracks) trackIdCounts.set(track.id, (trackIdCounts.get(track.id) ?? 0) + 1);
    const assertReferencedTrackIdUnique = (trackId: string) => {
      if ((trackIdCounts.get(trackId) ?? 0) > 1) throw new CommandError(`CROSS_TRACK_TRACK_ID_AMBIGUOUS: ${trackId}`);
    };
    let selectionKind: Track["kind"] | null = null;
    for (const move of moves) {
      assertReferencedTrackIdUnique(move.sourceTrackId);
      assertReferencedTrackIdUnique(move.targetTrackId);
      if (selectedIds.has(move.clipId)) throw new CommandError(`CROSS_TRACK_DUPLICATE_CLIP_ID: ${move.clipId}`);
      selectedIds.add(move.clipId);
      const containments = prev.tracks.flatMap((track) =>
        track.clips.filter((clip) => clip.id === move.clipId).map((clip) => ({ clip, track })),
      );
      if (containments.length > 1) throw new CommandError(`CROSS_TRACK_CLIP_ID_AMBIGUOUS: ${move.clipId}`);
      let found: { clip: Clip; track: Track };
      try {
        found = containments[0] ?? findClip(prev, move.clipId);
      } catch (error) {
        if (error instanceof CommandError && error.message.startsWith("CLIP_NOT_FOUND:")) {
          throw new CommandError(`CROSS_TRACK_CLIP_NOT_FOUND: ${move.clipId}`);
        }
        throw error;
      }
      const { clip, track: source } = found;
      if (source.id !== move.sourceTrackId || clip.trackId !== source.id) {
        throw new CommandError(`CROSS_TRACK_SOURCE_TRACK_DRIFT: ${move.clipId}`);
      }
      if (source.kind !== "video" && source.kind !== "audio") throw new CommandError(`CROSS_TRACK_TRACK_KIND_UNSUPPORTED: ${source.kind}`);
      if (selectionKind !== null && source.kind !== selectionKind) throw new CommandError("CROSS_TRACK_SELECTION_KIND_MISMATCH");
      selectionKind = source.kind;
      assertTrackUnlocked(source);
      const target = prev.tracks.find((candidate) => candidate.id === move.targetTrackId);
      if (!target) throw new CommandError(`CROSS_TRACK_TARGET_TRACK_NOT_FOUND: ${move.targetTrackId}`);
      if (target.kind !== source.kind) throw new CommandError(`CROSS_TRACK_TARGET_TRACK_KIND_MISMATCH: ${move.targetTrackId}`);
      assertTrackUnlocked(target);
      resolved.push({ ...move, clip, source, target });
    }
    if (resolved.every((move) => move.source.id === move.target.id && move.clip.start === move.newStart)) {
      throw new CommandError("CROSS_TRACK_NO_OP");
    }

    // Prove no one-sided crossfade can be detached before constructing state.
    assertTransitionTopology(prev, prev, selectedIds);
    const movedById = new Map(resolved.map((move) => [move.clipId, move]));
    const incoming = new Map<string, Clip[]>();
    for (const move of resolved) {
      const destination = incoming.get(move.target.id) ?? [];
      destination.push({ ...move.clip, start: move.newStart, trackId: move.target.id });
      incoming.set(move.target.id, destination);
    }
    const tracks = prev.tracks.map((track) => ({
      ...track,
      clips: [
        ...track.clips.filter((clip) => !movedById.has(clip.id)),
        ...(incoming.get(track.id) ?? []),
      ],
    }));
    const snapshot: CrossTrackSnapshot = { tracks: prev.tracks, durationSec: prev.durationSec };
    const next: Project = { ...prev, tracks, durationSec: Math.max(recomputeDuration({ ...prev, tracks }), prev.durationSec), updatedAt: new Date().toISOString() };
    assertTransitionTopology(prev, next, selectedIds);
    return { next, inverse: { type: MOVE_CLIP_ACROSS_TRACKS, execute: (project) => restoreCrossTrackSnapshot(project, snapshot) } };
  },
};

/* ----------------------------- clipAudio ---------------------------- */
export const SET_CLIP_AUDIO = "clip.audio";
export const setClipAudioSchema = z.object({
  clipId: z.string().min(1),
  gainDb: z.number().min(-60).max(0),
  muted: z.boolean(),
});
export const setClipAudioCommand: EditCommand<z.infer<typeof setClipAudioSchema>> = {
  type: SET_CLIP_AUDIO,
  schema: setClipAudioSchema,
  execute(prev, { clipId, gainDb, muted }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const prior = clip.audio ?? { gainDb: 0, muted: false };
    const updated: Clip = { ...clip, audio: { gainDb, muted } };
    const tracks = prev.tracks.map((t) =>
      t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t,
    );
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
export const setClipEffectsCommand: EditCommand<z.infer<typeof setClipEffectsSchema>> = {
  type: SET_CLIP_EFFECTS,
  schema: setClipEffectsSchema,
  execute(prev, { clipId, brightness, contrast, saturation }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const prior = clip.effects ?? { brightness: 0, contrast: 1, saturation: 1 };
    const updated: Clip = { ...clip, effects: { brightness, contrast, saturation } };
    const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
    return { next: { ...prev, tracks, updatedAt: new Date().toISOString() }, inverse: { type: SET_CLIP_EFFECTS, execute: (p) => setClipEffectsCommand.execute(p, { clipId, ...prior }) } };
  },
};

/* ---------------------------- clipSpeed ----------------------------- */
export const SET_CLIP_SPEED = "clip.speed";
export const setClipSpeedSchema = z.object({ clipId: z.string().min(1), playbackRate: z.number().min(0.25).max(4) });
export const setClipSpeedCommand: EditCommand<z.infer<typeof setClipSpeedSchema>> = {
  type: SET_CLIP_SPEED, schema: setClipSpeedSchema,
  execute(prev, { clipId, playbackRate }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const priorRate = clip.playbackRate ?? 1;
    const duration = clip.duration * priorRate / playbackRate;
    if (clip.transitionIn && clip.transitionIn.duration > duration + 1e-9) throw new CommandError("SPEED_CONFLICTS_WITH_TRANSITION");
    const updated: Clip = { ...clip, playbackRate, duration };
    const ordered = track.clips.map((c) => c.id === clipId ? updated : c).sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const changedIndex = ordered.findIndex((c) => c.id === clipId);
    for (let i = changedIndex + 1; i < ordered.length; i += 1) {
      const current = ordered[i];
      if (!current.transitionIn) break;
      const previous = ordered[i - 1];
      ordered[i] = { ...current, start: previous.start + previous.duration - current.transitionIn.duration };
    }
    const byId = new Map(ordered.map((c) => [c.id, c] as const));
    const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => byId.get(c.id) ?? c) } : t);
    const next: Project = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
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

type TransitionSnapshot = { start: number; transitionIn: Clip["transitionIn"] };
function restoreClipTransition(prev: Project, clipId: string, target: TransitionSnapshot): { next: Project; inverse: EditCommand } {
  const { clip, track } = findClip(prev, clipId);
  const current: TransitionSnapshot = { start: clip.start, transitionIn: clip.transitionIn ?? null };
  const updated: Clip = { ...clip, start: target.start, transitionIn: target.transitionIn };
  const tracks = prev.tracks.map((t) => t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t);
  const next: Project = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
  return { next, inverse: { type: SET_CLIP_TRANSITION, execute: (p: Project) => restoreClipTransition(p, clipId, current) } as EditCommand };
}

export const setClipTransitionCommand: EditCommand<z.infer<typeof setClipTransitionSchema>> = {
  type: SET_CLIP_TRANSITION,
  schema: setClipTransitionSchema,
  execute(prev, { clipId, mode, duration }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    if (track.kind !== "video") throw new CommandError("TRANSITION_REQUIRES_VIDEO_TRACK");
    const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const index = ordered.findIndex((c) => c.id === clipId);
    const previous = index > 0 ? ordered[index - 1] : undefined;
    if (mode === "crossfade") {
      if (!previous) throw new CommandError("TRANSITION_REQUIRES_PREVIOUS_CLIP");
      const d = duration ?? 0.5;
      const maxDuration = Math.min(previous.duration, clip.duration, 2);
      if (d > maxDuration + 1e-9) throw new CommandError(`TRANSITION_TOO_LONG: ${d} > ${maxDuration}`);
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
export const setClipTransformCommand: EditCommand<z.infer<typeof setClipTransformSchema>> = {
  type: SET_CLIP_TRANSFORM,
  schema: setClipTransformSchema,
  execute(prev, { clipId, scale, x, y, opacity }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const prior = clip.transform ?? { scale: 1, x: 0, y: 0, opacity: 1 };
    const updated: Clip = { ...clip, transform: { scale, x, y, opacity } };    const tracks = prev.tracks.map((t) =>
      t.id === track.id ? { ...t, clips: t.clips.map((c) => c.id === clipId ? updated : c) } : t,
    );
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

type RippleSnapshot = { trackId: string; clips: Clip[] };
function restoreRippleSnapshot(prev: Project, snapshots: RippleSnapshot[]): { next: Project; inverse: EditCommand } {
  const wanted = new Map(snapshots.map((s) => [s.trackId, s.clips] as const));
  const current = prev.tracks.filter((t) => wanted.has(t.id)).map((t) => ({ trackId: t.id, clips: t.clips }));
  const tracks = prev.tracks.map((t) => wanted.has(t.id) ? { ...t, clips: wanted.get(t.id)! } : t);
  const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
  return { next, inverse: { type: "clip.rippleRestore", execute: (p) => restoreRippleSnapshot(p, current) } };
}

function mergeIntervals(intervals: Array<{ start: number; end: number }>) {
  const ordered = [...intervals].sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: Array<{ start: number; end: number }> = [];
  for (const interval of ordered) {
    const last = merged[merged.length - 1];
    if (last && interval.start <= last.end + 1e-9) last.end = Math.max(last.end, interval.end);
    else merged.push({ ...interval });
  }
  return merged;
}

export const rippleDeleteClipsCommand: EditCommand<z.infer<typeof rippleDeleteClipsSchema>> = {
  type: RIPPLE_DELETE_CLIPS,
  schema: rippleDeleteClipsSchema,
  execute(prev, { clipIds }) {
    if (new Set(clipIds).size !== clipIds.length) throw new CommandError("RIPPLE_DUPLICATE_CLIP_ID");
    const selected = new Set(clipIds);
    for (const id of clipIds) findClip(prev, id);
    const affected = prev.tracks.filter((t) => t.clips.some((c) => selected.has(c.id)));
    for (const track of affected) assertTrackUnlocked(track);
    const snapshots = affected.map((t) => ({ trackId: t.id, clips: t.clips }));
    const replacements = new Map<string, Clip[]>();
    for (const track of affected) {
      const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
      for (let i = 0; i < ordered.length; i += 1) {
        if (!selected.has(ordered[i].id)) continue;
        const prevClip = ordered[i - 1];
        const nextClip = ordered[i + 1];
        if (ordered[i].transitionIn && prevClip && !selected.has(prevClip.id)) throw new CommandError("RIPPLE_TRANSITION_CONFLICT");
        if (nextClip?.transitionIn && !selected.has(nextClip.id)) throw new CommandError("RIPPLE_TRANSITION_CONFLICT");
      }
      const intervals = mergeIntervals(ordered.filter((c) => selected.has(c.id)).map((c) => ({ start: c.start, end: c.start + c.duration })));
      const remaining = ordered.filter((c) => !selected.has(c.id)).map((clip) => {
        for (const interval of intervals) {
          if (clip.start < interval.end - 1e-9 && clip.start + clip.duration > interval.start + 1e-9) throw new CommandError("RIPPLE_OVERLAP_CONFLICT");
        }
        const shift = intervals.filter((x) => x.end <= clip.start + 1e-9).reduce((sum, x) => sum + x.end - x.start, 0);
        return shift > 0 ? { ...clip, start: Math.max(0, clip.start - shift) } : clip;
      });
      replacements.set(track.id, remaining);
    }
    const tracks = prev.tracks.map((t) => replacements.has(t.id) ? { ...t, clips: replacements.get(t.id)! } : t);
    const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
    return { next, inverse: { type: "clip.rippleRestore", execute: (p) => restoreRippleSnapshot(p, snapshots) } };
  },
};

export const rippleTrimClipCommand: EditCommand<z.infer<typeof rippleTrimClipSchema>> = {
  type: RIPPLE_TRIM_CLIP,
  schema: rippleTrimClipSchema,
  execute(prev, { clipId, newInPoint, newSourceEnd }) {
    if (newInPoint === undefined && newSourceEnd === undefined) throw new CommandError("INVALID_RIPPLE_TRIM");
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const asset = findAsset(prev, clip.assetId);
    const rate = clip.playbackRate ?? 1;
    const sourceEnd = clip.inPoint + clip.duration * rate;
    let updated: Clip;
    if (newSourceEnd !== undefined) {
      const sourceSpan = newSourceEnd - clip.inPoint;
      if (sourceSpan <= 0) throw new CommandError("INVALID_RIPPLE_TRIM");
      updated = { ...clip, duration: sourceSpan / rate };
    } else {
      const nip = newInPoint as number;
      const sourceSpan = sourceEnd - nip;
      if (sourceSpan <= 0) throw new CommandError("INVALID_RIPPLE_TRIM");
      updated = { ...clip, inPoint: nip, duration: sourceSpan / rate };
    }
    const bad = validateClipAgainstAsset(updated, asset);
    if (bad) throw new CommandError(`INVALID_RIPPLE_TRIM: ${bad}`);
    if (updated.transitionIn && updated.transitionIn.duration > updated.duration + 1e-9) throw new CommandError("RIPPLE_TRIM_TRANSITION_CONFLICT");
    const ordered = [...track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const index = ordered.findIndex((c) => c.id === clipId);
    const nextClip = ordered[index + 1];
    if (nextClip?.transitionIn && nextClip.transitionIn.duration > updated.duration + 1e-9) throw new CommandError("RIPPLE_TRIM_TRANSITION_CONFLICT");
    const delta = updated.duration - clip.duration;
    const changed = ordered.map((c, i) => i === index ? updated : i > index ? { ...c, start: c.start + delta } : c);
    if (changed.some((c) => c.start < -1e-9)) throw new CommandError("RIPPLE_TRIM_NEGATIVE_START");
    const byId = new Map(changed.map((c) => [c.id, { ...c, start: Math.max(0, c.start) }] as const));
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
export const trimClipCommand: EditCommand<z.infer<typeof trimClipSchema>> = {
  type: TRIM_CLIP,
  schema: trimClipSchema,
  execute(prev, { clipId, newInPoint, newSourceEnd }) {
    if (newInPoint === undefined && newSourceEnd === undefined) {
      throw new CommandError("INVALID_TRIM: provide newInPoint or newSourceEnd");
    }
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    const asset = findAsset(prev, clip.assetId);
    const rate = clip.playbackRate ?? 1;
    const originalSourceEnd = clip.inPoint + clip.duration * rate;
    let updated: Clip = clip;
    if (newSourceEnd !== undefined) {
      const sourceSpan = newSourceEnd - clip.inPoint;
      const duration = sourceSpan / rate;
      if (duration <= 0) throw new CommandError(`INVALID_TRIM: duration ${duration}`);
      updated = { ...clip, duration };
    } else {
      const nip = newInPoint as number;
      const duration = (originalSourceEnd - nip) / rate;
      if (duration <= 0) throw new CommandError(`INVALID_TRIM: duration ${duration}`);
      updated = { ...clip, inPoint: nip, duration };
    }
    const bad = validateClipAgainstAsset(updated, asset);
    if (bad) throw new CommandError(`INVALID_TRIM: ${bad}`);
    if (updated.transitionIn && updated.transitionIn.duration > updated.duration + 1e-9) throw new CommandError("TRIM_TRANSITION_CONFLICT");
    const tracks = prev.tracks.map((t) =>
      t.id === track.id ? { ...t, clips: t.clips.map((c) => (c.id === clipId ? updated : c)) } : t,
    );
    const next: Project = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
    return {
      next,
      inverse: {
        type: TRIM_CLIP,
        execute: (p) => trimClipCommand.execute(
          p,
          newSourceEnd !== undefined
            ? { clipId, newSourceEnd: originalSourceEnd }
            : { clipId, newInPoint: clip.inPoint },
        ),
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
  targetTrackId: z.string().min(1).optional(),
});
export const placeCaptionCommand: EditCommand<z.infer<typeof placeCaptionSchema>> = {
  type: PLACE_CAPTION,
  schema: placeCaptionSchema,
  execute(prev, { text, start, duration, targetTrackId }) {
    const compatible = prev.tracks.filter((track) => track.kind === "text");
    let existing: Track | undefined;
    if (targetTrackId) {
      const target = prev.tracks.find((track) => track.id === targetTrackId);
      if (!target) throw new CommandError(`CAPTION_TARGET_TRACK_NOT_FOUND: ${targetTrackId}`);
      if (target.kind !== "text") throw new CommandError(`CAPTION_TARGET_TRACK_KIND_MISMATCH: ${target.kind}`);
      existing = target;
    } else if (compatible.length > 1) {
      throw new CommandError("CAPTION_TARGET_TRACK_REQUIRED");
    } else existing = compatible[0];
    if (existing) assertTrackUnlocked(existing);
    const trackId = existing?.id ?? "text-captions";
    const used = new Set(prev.tracks.flatMap((t) => t.captions.map((c) => c.id)));
    let n = 1;
    while (used.has(`cap-${n}`)) n += 1;
    const caption = {
      id: `cap-${n}`, text, start, duration, trackId,
      style: { x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.6 },
    };
    const tracks = existing
      ? prev.tracks.map((t) => t.id === trackId ? { ...t, captions: [...t.captions, caption] } : t)
      : [...prev.tracks, { id: trackId, kind: "text" as const, clips: [], captions: [caption], visible: true, muted: false, locked: false }];
    const next: Project = {
      ...prev, tracks,
      durationSec: Math.max(prev.durationSec, start + duration),
      updatedAt: new Date().toISOString(),
    };
    const inverse: EditCommand<z.infer<typeof placeCaptionSchema>> = {
      type: "caption.unplace",
      execute(p) {
        const track = p.tracks.find((t) => t.id === trackId);
        if (!track) throw new CommandError(`CAPTION_TRACK_NOT_FOUND: ${trackId}`);
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
export const addCaptionCommand: EditCommand<z.infer<typeof addCaptionSchema>> = {
  type: ADD_CAPTION,
  schema: addCaptionSchema,
  execute(prev, { caption }) {
    const targetTrack = findTrack(prev, caption.trackId);
    assertTrackUnlocked(targetTrack);
    if (targetTrack.kind !== "text") throw new CommandError(`CAPTION_TRACK_KIND_MISMATCH: ${targetTrack.kind}`);
    if (prev.tracks.some((t) => t.captions.some((c) => c.id === caption.id))) {
      throw new CommandError(`CAPTION_DUPLICATE: ${caption.id}`);
    }
    const tracks = prev.tracks.map((t) =>
      t.id === caption.trackId ? { ...t, captions: [...t.captions, caption] } : t,
    );
    const next: Project = {
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
export const removeCaptionCommand: EditCommand<{ captionId: string; trackId: string }> = {
  type: REMOVE_CAPTION,
  execute(prev, { captionId, trackId }) {
    const track = findTrack(prev, trackId);
    assertTrackUnlocked(track);
    const caption = track.captions.find((c) => c.id === captionId);
    if (!caption) throw new CommandError(`CAPTION_NOT_FOUND: ${captionId}`);
    const tracks = prev.tracks.map((t) =>
      t.id === trackId ? { ...t, captions: t.captions.filter((c) => c.id !== captionId) } : t,
    );
    const next: Project = { ...prev, tracks, updatedAt: new Date().toISOString() };
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
export const changeAspectCommand: EditCommand<z.infer<typeof changeAspectSchema>> = {
  type: CHANGE_ASPECT,
  schema: changeAspectSchema,
  execute(prev, { ratio }) {
    if (prev.aspectRatio === ratio) {
      return { next: prev, inverse: changeAspectCommand };
    }
    const prior = prev.aspectRatio;
    const next: Project = { ...prev, aspectRatio: ratio, updatedAt: new Date().toISOString() };
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
// Multiple video/audio/text tracks are allowed. Track identity is unique by id.
// Placement commands must resolve an explicit or unambiguous compatible target.
export const ADD_TRACK = "track.add";
export const addTrackSchema = z.object({
  track: z.object({
    id: z.string().min(1),
    kind: z.enum(["video", "audio", "text"]),
    clips: z.array(clipSchema).default([]),
    captions: z.array(captionSchema).default([]),
    visible: z.boolean().default(true),
    muted: z.boolean().default(false),
    locked: z.boolean().default(false),
  }),
});
export const addTrackCommand: EditCommand<z.infer<typeof addTrackSchema>> = {
  type: ADD_TRACK,
  schema: addTrackSchema,
  execute(prev, { track }) {
    if (prev.tracks.some((t) => t.id === track.id)) {
      throw new CommandError(`TRACK_DUPLICATE_ID: ${track.id}`);
    }
    const next: Project = {
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
export const removeTrackCommand: EditCommand<{ trackId: string }> = {
  type: REMOVE_TRACK,
  execute(prev, { trackId }) {
    const track = findTrack(prev, trackId);
    assertTrackUnlocked(track);
    const next: Project = {
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

export const REORDER_TRACK = "track.reorder";
export const reorderTrackSchema = z.object({
  trackId: z.string().min(1),
  toIndex: z.number().int().nonnegative(),
});
export const reorderTrackCommand: EditCommand<z.infer<typeof reorderTrackSchema>> = {
  type: REORDER_TRACK,
  schema: reorderTrackSchema,
  execute(prev, { trackId, toIndex }) {
    const track = findTrack(prev, trackId);
    assertTrackUnlocked(track);
    const fromIndex = prev.tracks.findIndex((candidate) => candidate.id === trackId);
    if (toIndex >= prev.tracks.length) throw new CommandError(`TRACK_INDEX_OUT_OF_RANGE: ${toIndex}`);
    if (fromIndex === toIndex) return { next: prev, inverse: reorderTrackCommand };
    const tracks = [...prev.tracks];
    tracks.splice(fromIndex, 1);
    tracks.splice(toIndex, 0, track);
    return {
      next: { ...prev, tracks, updatedAt: new Date().toISOString() },
      inverse: { type: REORDER_TRACK, execute: (p) => reorderTrackCommand.execute(p, { trackId, toIndex: fromIndex }) },
    };
  },
};

export const SET_TRACK_CONTROLS = "track.setControls";
export const setTrackControlsSchema = z.object({
  trackId: z.string().min(1),
  visible: z.boolean().optional(),
  muted: z.boolean().optional(),
  locked: z.boolean().optional(),
}).refine((value) => value.visible !== undefined || value.muted !== undefined || value.locked !== undefined, {
  message: "provide at least one track control",
});
export const setTrackControlsCommand: EditCommand<z.infer<typeof setTrackControlsSchema>> = {
  type: SET_TRACK_CONTROLS,
  schema: setTrackControlsSchema,
  execute(prev, { trackId, visible, muted, locked }) {
    const track = findTrack(prev, trackId);
    const prior = { visible: track.visible, muted: track.muted, locked: track.locked };
    const updated: Track = {
      ...track,
      visible: visible ?? track.visible,
      muted: muted ?? track.muted,
      locked: locked ?? track.locked,
    };
    const tracks = prev.tracks.map((candidate) => candidate.id === trackId ? updated : candidate);
    return {
      next: { ...prev, tracks, updatedAt: new Date().toISOString() },
      inverse: { type: SET_TRACK_CONTROLS, execute: (p) => setTrackControlsCommand.execute(p, { trackId, ...prior }) },
    };
  },
};

function resolveMediaTargetTrack(
  project: Project,
  kind: "video" | "audio",
  targetTrackId: string | undefined,
  createTrackId: string,
): { tracks: Track[]; track: Track; created: boolean } {
  if (targetTrackId) {
    const track = project.tracks.find((candidate) => candidate.id === targetTrackId);
    if (!track) throw new CommandError(`TIMELINE_TARGET_TRACK_NOT_FOUND: ${targetTrackId}`);
    if (track.kind !== kind) throw new CommandError(`TIMELINE_TARGET_TRACK_KIND_MISMATCH: ${track.kind} != ${kind}`);
    assertTrackUnlocked(track);
    return { tracks: project.tracks, track, created: false };
  }
  const compatible = project.tracks.filter((candidate) => candidate.kind === kind);
  if (compatible.length > 1) throw new CommandError(`TIMELINE_TARGET_TRACK_REQUIRED: ${kind}`);
  if (compatible.length === 1) {
    assertTrackUnlocked(compatible[0]);
    return { tracks: project.tracks, track: compatible[0], created: false };
  }
  if (project.tracks.some((candidate) => candidate.id === createTrackId)) {
    throw new CommandError(`TIMELINE_TRACK_ID_CONFLICT: ${createTrackId}`);
  }
  const track: Track = {
    id: createTrackId, kind, clips: [], captions: [], visible: true, muted: false, locked: false,
  };
  return { tracks: [...project.tracks, track], track, created: true };
}

/* ----------------------------- placeProbedMedia --------------------- */
// Atomic import+place. A single CommandBus operation that:
//   1. validates the probe (must be a successful probe)
//   2. builds the immutable MediaAsset
//   3. resolves an explicit/unambiguous compatible target track, creating one only when none exists
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
  targetTrackId: z.string().min(1).optional(),
});
export const placeProbedMediaCommand: EditCommand<z.infer<typeof placeProbedMediaSchema>> = {
  type: PLACE_PROBED_MEDIA,
  schema: placeProbedMediaSchema,
  execute(prev, { probe, place, targetTrackId }) {
    if (probe.probeStatus !== "ok") {
      throw new CommandError(`PROBE_NOT_OK: ${probe.probeStatus}`);
    }
    if (prev.assets.some((a) => a.id === probe.id)) {
      throw new CommandError(`ASSET_DUPLICATE: ${probe.id}`);
    }
    const assetKind = probe.kind === "audio" ? "audio" : probe.kind === "video" ? "video" : "image";
    const trackKind: "video" | "audio" = assetKind === "audio" ? "audio" : "video";

    const asset: MediaAsset = {
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
    let tracks = prev.tracks;
    let resolvedTargetTrackId: string | undefined;
    let createdTrackId: string | undefined;
    if (place) {
      const resolved = resolveMediaTargetTrack(prev, trackKind, targetTrackId, newTrackId);
      tracks = resolved.tracks;
      resolvedTargetTrackId = resolved.track.id;
      if (resolved.created) createdTrackId = resolved.track.id;
    }

    let next: Project = {
      ...prev,
      assets: [...prev.assets, asset],
      tracks,
      updatedAt: new Date().toISOString(),
    };

    let clipId: string | undefined;
    if (place) {
      const track = next.tracks.find((t) => t.id === resolvedTargetTrackId)!;
      const start = Math.max(0, ...track.clips.map((c) => c.start + c.duration));
      clipId = `${probe.id}-clip`;
      const clip: Clip = {
        id: clipId,
        assetId: asset.id,
        inPoint: 0,
        duration: asset.durationSec,
        start,
        trackId: resolvedTargetTrackId!,
        transform: { scale: 1, x: 0, y: 0, opacity: 1 },
        audio: { gainDb: 0, muted: false },
        effects: { brightness: 0, contrast: 1, saturation: 1 },
        playbackRate: 1,
        transitionIn: null,
      };
      next = {
        ...next,
        tracks: next.tracks.map((t) => (t.id === resolvedTargetTrackId ? { ...t, clips: [...t.clips, clip] } : t)),
      };
      next = { ...next, durationSec: Math.max(recomputeDuration(next), next.durationSec) };
    }

    const inverse: EditCommand<z.infer<typeof placeProbedMediaSchema>> = {
      type: "media.unplaceProbed",
      execute(p, { probe: pr, place: pl }) {
        let tracks = p.tracks;
        if (createdTrackId) tracks = tracks.filter((track) => track.id !== createdTrackId);
        else if (pl && resolvedTargetTrackId) {
          tracks = tracks.map((track) => track.id === resolvedTargetTrackId
            ? { ...track, clips: track.clips.filter((clip) => clip.id !== `${pr.id}-clip`) }
            : track);
        }
        const r: Project = {
          ...p,
          assets: p.assets.filter((asset) => asset.id !== pr.id),
          tracks,
          durationSec: recomputeDuration({ ...p, tracks }),
        };
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
  targetTrackId: z.string().min(1).optional(),
});

type TimelineAssetEdit = z.infer<typeof timelineAssetEditSchema>;

function restoreTimelineEditSnapshot(prev: Project, snapshot: Project): { next: Project; inverse: EditCommand } {
  const current = prev;
  return {
    next: snapshot,
    inverse: { type: "timeline.restore", execute: (p) => restoreTimelineEditSnapshot(p, current) },
  };
}

function timelineTrackKind(asset: MediaAsset): "video" | "audio" {
  return asset.kind === "audio" ? "audio" : "video";
}


function makeTimelineEditClip(asset: MediaAsset, trackId: string, clipId: string, atSec: number): Clip {
  return {
    id: clipId, assetId: asset.id, inPoint: 0, duration: asset.durationSec, start: atSec, trackId,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    audio: { gainDb: 0, muted: false },
    effects: { brightness: 0, contrast: 1, saturation: 1 },
    playbackRate: 1, transitionIn: null,
  };
}

function assertTimelineClipIdAvailable(project: Project, clipId: string): void {
  if (project.tracks.some((t) => t.clips.some((c) => c.id === clipId))) {
    throw new CommandError(`TIMELINE_CLIP_ID_DUPLICATE: ${clipId}`);
  }
}

function ensureTimelineTrack(project: Project, asset: MediaAsset, targetTrackId?: string): { tracks: Track[]; track: Track } {
  const kind = timelineTrackKind(asset);
  const resolved = resolveMediaTargetTrack(project, kind, targetTrackId, `timeline-${kind}`);
  return { tracks: resolved.tracks, track: resolved.track };
}


export const timelineInsertAssetCommand: EditCommand<TimelineAssetEdit> = {
  type: TIMELINE_INSERT_ASSET,
  schema: timelineAssetEditSchema,
  execute(prev, { assetId, clipId, atSec, targetTrackId }) {
    const asset = findAsset(prev, assetId);
    assertTimelineClipIdAvailable(prev, clipId);
    const ensured = ensureTimelineTrack(prev, asset, targetTrackId);
    const ordered = [...ensured.track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const covering = ordered.filter((c) => c.start < atSec - 1e-9 && c.start + c.duration > atSec + 1e-9);
    if (covering.length > 1) throw new CommandError("TIMELINE_OVERLAP_CONFLICT");
    const nextAtBoundary = ordered.find((c) => c.start >= atSec - 1e-9);
    if (covering[0]?.transitionIn || nextAtBoundary?.transitionIn) throw new CommandError("TIMELINE_TRANSITION_CONFLICT");
    const inserted = makeTimelineEditClip(asset, ensured.track.id, clipId, atSec);
    const badInserted = validateClipAgainstAsset(inserted, asset);
    if (badInserted) throw new CommandError(`INVALID_TIMELINE_EDIT: ${badInserted}`);
    const split = covering[0];
    const replacement: Clip[] = [];


    for (const c of ordered) {
      if (split && c.id === split.id) {
        const leftDuration = atSec - c.start;
        const rightDuration = c.start + c.duration - atSec;
        const rate = c.playbackRate ?? 1;
        const rightId = `${c.id}__insert_r_${clipId}`;
        assertTimelineClipIdAvailable(prev, rightId);
        const right: Clip = {
          ...c, id: rightId, start: atSec + asset.durationSec,
          inPoint: c.inPoint + leftDuration * rate, duration: rightDuration,
        };
        const left: Clip = { ...c, duration: leftDuration };
        if (validateClipAgainstAsset(left, findAsset(prev, left.assetId)) || validateClipAgainstAsset(right, findAsset(prev, right.assetId))) {
          throw new CommandError("INVALID_TIMELINE_INSERT_SPLIT");
        }
        replacement.push(left, right);
      } else if (c.start >= atSec - 1e-9) replacement.push({ ...c, start: c.start + asset.durationSec });
      else replacement.push(c);
    }
    replacement.push(inserted);
    replacement.sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const tracks = ensured.tracks.map((t) => t.id === ensured.track.id ? { ...t, clips: replacement } : t);
    const next = { ...prev, tracks, durationSec: recomputeDuration({ ...prev, tracks }), updatedAt: new Date().toISOString() };
    return { next, inverse: { type: "timeline.restore", execute: (p) => restoreTimelineEditSnapshot(p, prev) } };
  },
};


export const timelineOverwriteAssetCommand: EditCommand<TimelineAssetEdit> = {
  type: TIMELINE_OVERWRITE_ASSET,
  schema: timelineAssetEditSchema,
  execute(prev, { assetId, clipId, atSec, targetTrackId }) {
    const asset = findAsset(prev, assetId);
    assertTimelineClipIdAvailable(prev, clipId);
    const ensured = ensureTimelineTrack(prev, asset, targetTrackId);
    const ordered = [...ensured.track.clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
    const endSec = atSec + asset.durationSec;
    for (let i = 1; i < ordered.length; i += 1) {
      const a = ordered[i - 1], b = ordered[i];
      if (b.start < a.start + a.duration - 1e-9 && b.start < endSec - 1e-9 && a.start + a.duration > atSec + 1e-9) {
        throw new CommandError("TIMELINE_OVERLAP_CONFLICT");
      }
    }
    const transitionConflict = ordered.some((c) => c.transitionIn && c.start <= endSec + 1e-9 && c.start + c.duration >= atSec - 1e-9);
    if (transitionConflict) throw new CommandError("TIMELINE_TRANSITION_CONFLICT");
    const inserted = makeTimelineEditClip(asset, ensured.track.id, clipId, atSec);
    const replacement: Clip[] = [];


    for (const c of ordered) {
      const clipEnd = c.start + c.duration;
      if (clipEnd <= atSec + 1e-9 || c.start >= endSec - 1e-9) {
        replacement.push(c);
        continue;
      }
      const keepLeft = c.start < atSec - 1e-9;
      const keepRight = clipEnd > endSec + 1e-9;
      const rate = c.playbackRate ?? 1;
      if (keepLeft) replacement.push({ ...c, duration: atSec - c.start });
      if (keepRight) {
        const rightId = keepLeft ? `${c.id}__overwrite_r_${clipId}` : c.id;
        if (keepLeft) assertTimelineClipIdAvailable(prev, rightId);
        const right: Clip = {
          ...c,
          id: rightId,
          start: endSec,
          inPoint: c.inPoint + (endSec - c.start) * rate,
          duration: clipEnd - endSec,
        };
        if (validateClipAgainstAsset(right, findAsset(prev, right.assetId))) throw new CommandError("INVALID_TIMELINE_OVERWRITE_SPLIT");
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
export const relinkMediaCommand: EditCommand<z.infer<typeof relinkMediaSchema>> = {
  type: RELINK_MEDIA,
  schema: relinkMediaSchema,
  execute(prev, { assetId, probe }) {
    if (probe.probeStatus !== "ok") throw new CommandError(`RELINK_PROBE_NOT_OK: ${probe.probeStatus}`);
    const prior = findAsset(prev, assetId);
    const nextKind = probe.kind === "audio" ? "audio" : probe.kind === "video" ? "video" : "image";
    if (nextKind !== prior.kind) throw new CommandError(`RELINK_KIND_MISMATCH: ${prior.kind} -> ${nextKind}`);
    const replacement: MediaAsset = {
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
        if (bad) throw new CommandError(`RELINK_INCOMPATIBLE_CLIP: ${clip.id}: ${bad}`);
      }
    }
    const next: Project = { ...prev, assets: prev.assets.map((a) => a.id === assetId ? replacement : a), updatedAt: new Date().toISOString() };
    const inverse: EditCommand<z.infer<typeof relinkMediaSchema>> = {
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
export const splitClipCommand: EditCommand<z.infer<typeof splitClipSchema>> = {
  type: SPLIT_CLIP,
  schema: splitClipSchema,
  execute(prev, { clipId, t }) {
    const { clip, track } = findClip(prev, clipId);
    assertTrackUnlocked(track);
    if (!(t > 0 && t < clip.duration)) {
      throw new CommandError(`INVALID_SPLIT_POINT: t=${t} must satisfy 0 < t < ${clip.duration}`);
    }
    const left: Clip = { ...clip, duration: t };
    const right: Clip = {
      ...clip,
      id: `${clip.id}__r`,
      inPoint: clip.inPoint + t,
      start: clip.start + t,
      duration: clip.duration - t,
    };
    const newClips = track.clips.flatMap((c) => (c.id === clipId ? [left, right] : [c]));
    const tracks = prev.tracks.map((tr) => (tr.id === track.id ? { ...tr, clips: newClips } : tr));
    const next: Project = {
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
          const merged: Clip = { ...left, duration: clip.duration };
          const mergedTracks = p.tracks.map((tr) =>
            tr.id === track.id
              ? { ...tr, clips: tr.clips.filter((c) => c.id !== right.id).map((c) => (c.id === left.id ? merged : c)) }
              : tr,
          );
          return {
            next: { ...p, tracks: mergedTracks, updatedAt: new Date().toISOString() },
            inverse: splitClipCommand,
          };
        },
      },
    };
  },
};
