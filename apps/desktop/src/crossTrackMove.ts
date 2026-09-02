import type { Project } from "@haios/project-model";

export interface TrackRect {
  trackId: string;
  top: number;
  bottom: number;
}

export interface CrossTrackMovePayload {
  clipId: string;
  sourceTrackId: string;
  targetTrackId: string;
  newStart: number;
}

export interface CrossTrackMovePlan {
  moves: CrossTrackMovePayload[];
  primaryDestinationTrackId: string;
  vertical: boolean;
}

export function resolveTrackAtClientY(rects: readonly TrackRect[], clientY: number): string | null {
  return rects.find((rect) => clientY >= rect.top && clientY < rect.bottom)?.trackId ?? null;
}

function fail(message: string): never {
  throw new Error(message);
}

function assertTrackIdUnique(project: Project, trackId: string): void {
  if (project.tracks.filter((track) => track.id === trackId).length > 1) {
    fail(`CROSS_TRACK_TRACK_ID_AMBIGUOUS: ${trackId}`);
  }
}

function clipsForSelection(project: Project, selectedClipIds: readonly string[]) {
  const all = project.tracks.flatMap((track) => track.clips.map((clip) => ({ clip, track })));
  const seen = new Set<string>();
  return selectedClipIds.map((clipId) => {
    if (seen.has(clipId)) fail(`CROSS_TRACK_DUPLICATE_CLIP_ID: ${clipId}`);
    seen.add(clipId);
    const matches = all.filter(({ clip }) => clip.id === clipId);
    if (matches.length > 1) fail(`CROSS_TRACK_CLIP_ID_AMBIGUOUS: ${clipId}`);
    const found = matches[0];
    if (!found) fail(`CROSS_TRACK_SELECTED_CLIP_NOT_FOUND: ${clipId}`);
    assertTrackIdUnique(project, found.track.id);
    if (found.clip.trackId !== found.track.id) fail(`CROSS_TRACK_SOURCE_TRACK_DRIFT: ${clipId}`);
    if (found.track.locked) fail(`TRACK_LOCKED: ${found.track.id}`);
    return found;
  });
}

/** Builds a deterministic, all-or-nothing selection move from Project track order. */
export function buildCrossTrackMovePlan(
  project: Project,
  selectedClipIds: readonly string[],
  anchorClipId: string,
  deltaSec: number,
  anchorTargetTrackId?: string | null,
): CrossTrackMovePlan {
  if (selectedClipIds.length === 0) fail("CROSS_TRACK_SELECTION_EMPTY");
  const selected = clipsForSelection(project, selectedClipIds);
  const anchor = selected.find(({ clip }) => clip.id === anchorClipId);
  if (!anchor) fail(`CROSS_TRACK_ANCHOR_NOT_SELECTED: ${anchorClipId}`);
  const minStart = Math.min(...selected.map(({ clip }) => clip.start + deltaSec));
  const appliedDelta = deltaSec + (minStart < 0 ? -minStart : 0);

  if (!anchorTargetTrackId || anchorTargetTrackId === anchor.track.id) {
    return {
      moves: selected.map(({ clip, track }) => ({ clipId: clip.id, sourceTrackId: track.id, targetTrackId: track.id, newStart: clip.start + appliedDelta })),
      primaryDestinationTrackId: anchor.track.id,
      vertical: false,
    };
  }

  assertTrackIdUnique(project, anchorTargetTrackId);
  const target = project.tracks.find((track) => track.id === anchorTargetTrackId);
  if (!target) fail(`CROSS_TRACK_TARGET_TRACK_NOT_FOUND: ${anchorTargetTrackId}`);
  if (target.locked) fail(`TRACK_LOCKED: ${target.id}`);
  if (target.kind !== anchor.track.kind) fail(`CROSS_TRACK_TARGET_TRACK_KIND_MISMATCH: ${target.id}`);
  if (anchor.track.kind !== "video" && anchor.track.kind !== "audio") fail(`CROSS_TRACK_TRACK_KIND_UNSUPPORTED: ${anchor.track.kind}`);
  if (selected.some(({ track }) => track.kind !== anchor.track.kind)) fail("CROSS_TRACK_SELECTION_KIND_MISMATCH");

  const compatibleTracks = project.tracks.filter((track) => track.kind === anchor.track.kind);
  const anchorSourceIndex = compatibleTracks.findIndex((track) => track.id === anchor.track.id);
  const anchorTargetIndex = compatibleTracks.findIndex((track) => track.id === target.id);
  const laneDelta = anchorTargetIndex - anchorSourceIndex;
  const moves = selected.map(({ clip, track }) => {
    const sourceIndex = compatibleTracks.findIndex((candidate) => candidate.id === track.id);
    const destination = compatibleTracks[sourceIndex + laneDelta];
    if (!destination) fail("CROSS_TRACK_DESTINATION_OUT_OF_RANGE");
    assertTrackIdUnique(project, destination.id);
    if (destination.locked) fail(`TRACK_LOCKED: ${destination.id}`);
    return { clipId: clip.id, sourceTrackId: track.id, targetTrackId: destination.id, newStart: clip.start + appliedDelta };
  });
  if (moves.every((move) => move.sourceTrackId === move.targetTrackId && move.newStart === selected.find(({ clip }) => clip.id === move.clipId)!.clip.start)) {
    fail("CROSS_TRACK_NO_OP");
  }
  return { moves, primaryDestinationTrackId: target.id, vertical: true };
}

export function isCrossTrackDestinationValid(project: Project, selectedClipIds: readonly string[], anchorClipId: string | null, targetTrackId: string): boolean {
  if (!anchorClipId) return false;
  try {
    return buildCrossTrackMovePlan(project, selectedClipIds, anchorClipId, 0, targetTrackId).vertical;
  } catch {
    return false;
  }
}
