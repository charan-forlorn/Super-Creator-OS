import type {
  Caption,
  Clip,
  CompositionAudioClip,
  CompositionPlan,
  MediaAsset,
} from "@haios/project-model";

export interface PreviewVisualClip {
  clip: Clip;
  asset: MediaAsset;
  opacity: number;
  sourceTimeSec: number;
}

export interface PreviewVisualLayer {
  trackId: string;
  zIndex: number;
  clips: PreviewVisualClip[];
}

export interface PreviewCaption {
  caption: Caption;
  trackId: string;
  zIndex: number;
}
export interface PreviewAudioEntry {
  trackId: string;
  mixIndex: number;
  clip: CompositionAudioClip;
  sourceTimeSec: number;
  gainScale: number;
}

export interface PreviewFrame {
  visualLayers: PreviewVisualLayer[];
  captions: PreviewCaption[];
  audio: PreviewAudioEntry[];
}

function isActive(start: number, duration: number, playheadSec: number): boolean {
  return playheadSec >= start && playheadSec < start + duration;
}

function sourceTime(clip: { start: number; inPoint: number; playbackRate: number }, playheadSec: number): number {
  return clip.inPoint + (playheadSec - clip.start) * clip.playbackRate;
}

function resolveVisualClips(
  clips: Clip[],
  playheadSec: number,
  assetById: Map<string, MediaAsset>,
): PreviewVisualClip[] {
  const ordered = [...clips].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
  const transitionIndex = ordered.findIndex((clip) =>
    clip.transitionIn?.type === "crossfade" &&
    playheadSec >= clip.start &&
    playheadSec < clip.start + clip.transitionIn.duration,
  );
  if (transitionIndex > 0) {
    const incoming = ordered[transitionIndex];
    const outgoing = ordered[transitionIndex - 1];
    const duration = incoming.transitionIn!.duration;
    const progress = Math.max(0, Math.min(1, (playheadSec - incoming.start) / duration));
    return [
      previewVisualClip(outgoing, 1 - progress, playheadSec, assetById),
      previewVisualClip(incoming, progress, playheadSec, assetById),
    ];
  }
  const active = ordered.find((clip) => isActive(clip.start, clip.duration, playheadSec));
  return active ? [previewVisualClip(active, 1, playheadSec, assetById)] : [];
}

function previewVisualClip(
  clip: Clip,
  opacity: number,
  playheadSec: number,
  assetById: Map<string, MediaAsset>,
): PreviewVisualClip {
  const asset = assetById.get(clip.assetId);
  if (!asset) throw new Error(`PREVIEW_ASSET_NOT_FOUND: ${clip.assetId}`);
  return { clip, asset, opacity, sourceTimeSec: sourceTime(clip, playheadSec) };
}
export function compilePreviewFrame(plan: CompositionPlan, playheadSec: number): PreviewFrame {
  const assetById = new Map(plan.assets.map((asset) => [asset.id, asset] as const));
  const visualLayers = plan.visualLayers
    .filter((layer) => layer.kind === "video")
    .map((layer) => ({
      trackId: layer.trackId,
      zIndex: layer.zIndex,
      clips: resolveVisualClips(layer.clips, playheadSec, assetById),
    }))
    .filter((layer) => layer.clips.length > 0);

  const captions = plan.visualLayers
    .filter((layer) => layer.kind === "text")
    .flatMap((layer) => layer.captions
      .filter((caption) => isActive(caption.start, caption.duration, playheadSec))
      .map((caption) => ({ caption, trackId: layer.trackId, zIndex: layer.zIndex })));

  const visualGainByClipId = new Map(visualLayers.flatMap((layer) =>
    layer.clips.map((entry) => [entry.clip.id, entry.opacity] as const)));
  const audio = plan.audioLayers.flatMap((layer) => layer.clips
    .filter((clip) => isActive(clip.startSec, clip.durationSec, playheadSec) || visualGainByClipId.has(clip.clipId))
    .map((clip) => ({
      trackId: layer.trackId, mixIndex: layer.mixIndex, clip,
      sourceTimeSec: clip.inPointSec + (playheadSec - clip.startSec) * clip.playbackRate,
      gainScale: visualGainByClipId.get(clip.clipId) ?? 1,
    })));

  return { visualLayers, captions, audio };
}
