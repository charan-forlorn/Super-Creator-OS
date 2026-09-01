import type { Caption, Clip, ExportResolution, MediaAsset, Project } from "./schema.js";

export interface CompositionVisualLayer {
  trackId: string;
  /** Project track index. Larger zIndex renders in front of smaller zIndex. */
  zIndex: number;
  kind: "video" | "text";
  clips: Clip[];
  captions: Caption[];
}

export interface CompositionAudioClip {
  clipId: string;
  assetId: string;
  sourcePath: string;
  startSec: number;
  inPointSec: number;
  durationSec: number;
  playbackRate: number;
  gainDb: number;
}

export interface CompositionAudioLayer {
  trackId: string;
  /** Project track index; audio layers are mixed, not replaced. */
  mixIndex: number;
  kind: "video" | "audio";
  clips: CompositionAudioClip[];
}

export interface CompositionPlan {
  schemaVersion: 2;
  durationSec: number;
  aspectRatio: ExportResolution;
  assets: MediaAsset[];
  visualLayers: CompositionVisualLayer[];
  audioLayers: CompositionAudioLayer[];
}

function cloneClip(clip: Clip): Clip {
  return {
    ...clip,
    transform: { ...clip.transform },
    effects: { ...clip.effects },
    audio: { ...clip.audio },
    transitionIn: clip.transitionIn ? { ...clip.transitionIn } : null,
  };
}

function cloneCaption(caption: Caption): Caption {
  return { ...caption, style: { ...caption.style } };
}

/**
 * Compile persisted Project v2 state into one JSON-serializable runtime plan.
 * Project track order is canonical: lower index is background, higher index foreground.
 * Visibility affects visuals only; mute affects audio only; lock is editing-only authority.
 */
export function compileCompositionPlan(project: Project): CompositionPlan {
  if (project.schemaVersion !== 2) {
    throw new Error(`COMPOSITION_SCHEMA_UNSUPPORTED: ${project.schemaVersion}`);
  }
  const assets = project.assets.map((asset) => ({ ...asset }));
  const assetById = new Map(assets.map((asset) => [asset.id, asset] as const));
  const visualLayers: CompositionVisualLayer[] = [];
  const audioLayers: CompositionAudioLayer[] = [];

  project.tracks.forEach((track, trackIndex) => {
    if (track.visible && (track.kind === "video" || track.kind === "text")) {
      visualLayers.push({
        trackId: track.id,
        zIndex: trackIndex,
        kind: track.kind,
        clips: track.clips.map(cloneClip),
        captions: track.captions.map(cloneCaption),
      });
    }

    if (!track.muted && (track.kind === "video" || track.kind === "audio")) {
      const audibleClips = track.clips.flatMap((clip) => {
        const asset = assetById.get(clip.assetId);
        if (!asset) throw new Error(`COMPOSITION_ASSET_NOT_FOUND: ${clip.assetId}`);
        if (clip.audio.muted || (track.kind === "video" && !asset.hasAudio)) return [];
        return [{ clipId: clip.id, assetId: clip.assetId, sourcePath: asset.sourcePath,
          startSec: clip.start, inPointSec: clip.inPoint, durationSec: clip.duration,
          playbackRate: clip.playbackRate, gainDb: clip.audio.gainDb }];
      });
      if (audibleClips.length) {
        audioLayers.push({ trackId: track.id, mixIndex: trackIndex, kind: track.kind, clips: audibleClips });
      }
    }
  });

  return {
    schemaVersion: 2,
    durationSec: project.durationSec,
    aspectRatio: project.aspectRatio,
    assets,
    visualLayers,
    audioLayers,
  };
}
