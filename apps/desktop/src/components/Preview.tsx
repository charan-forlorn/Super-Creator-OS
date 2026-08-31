import { useEffect, useRef, useState } from "react";
import { useStudio } from "../store";
import { resolvePreviewSource } from "../mediaUrl";
import { PlaybackDiagnostics } from "../previewDiagnostics";

export function Preview() {
  const { project, playheadSec, setPlayhead, previewProxies } = useStudio();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const outgoingRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const diagRef = useRef<PlaybackDiagnostics>(new PlaybackDiagnostics());

  const videoTrack = project.tracks.find((t) => t.kind === "video");
  const orderedClips = [...(videoTrack?.clips ?? [])].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
  const transitionIndex = orderedClips.findIndex((c) =>
    c.transitionIn?.type === "crossfade" &&
    playheadSec >= c.start && playheadSec < c.start + c.transitionIn.duration,
  );
  const transitionClip = transitionIndex >= 0 ? orderedClips[transitionIndex] : undefined;
  const outgoingClip = transitionIndex > 0 ? orderedClips[transitionIndex - 1] : undefined;
  const clip = transitionClip ?? orderedClips.find((c) => playheadSec >= c.start && playheadSec < c.start + c.duration);
  const transitionProgress = transitionClip?.transitionIn
    ? Math.max(0, Math.min(1, (playheadSec - transitionClip.start) / transitionClip.transitionIn.duration))
    : 1;

  const asset = clip ? project.assets.find((a) => a.id === clip.assetId) : undefined;
  const outgoingAsset = outgoingClip ? project.assets.find((a) => a.id === outgoingClip.assetId) : undefined;
  const previewSrc = asset ? resolvePreviewSource({ sourcePath: asset.sourcePath, proxyPath: previewProxies[asset.id] }) : undefined;
  const outgoingSrc = outgoingAsset ? resolvePreviewSource({ sourcePath: outgoingAsset.sourcePath, proxyPath: previewProxies[outgoingAsset.id] }) : undefined;
  const transitionActive = Boolean(transitionClip && outgoingClip && outgoingSrc && previewSrc);

  useEffect(() => {
    applyClipAudio(videoRef.current, clip, transitionActive ? transitionProgress : 1);
    applyClipAudio(outgoingRef.current, outgoingClip, transitionActive ? 1 - transitionProgress : 1);
    applyClipPlaybackRate(videoRef.current, clip);
    applyClipPlaybackRate(outgoingRef.current, outgoingClip);
  }, [clip, outgoingClip, transitionActive, transitionProgress]);

  useEffect(() => {
    syncVideoTime(videoRef.current, clip, playheadSec);
    syncVideoTime(outgoingRef.current, outgoingClip, playheadSec);
  }, [playheadSec, clip, outgoingClip]);

  function togglePlay() {
    const primary = videoRef.current;
    if (!primary) return;
    const videos = [outgoingRef.current, primary].filter((v): v is HTMLVideoElement => Boolean(v));
    if (primary.paused) {
      Promise.all(videos.map((v) => v.play())).then(() => setPlaying(true)).catch(() => setPlaying(false));
    } else {
      videos.forEach((v) => v.pause());
      setPlaying(false);
    }
  }

  function seekTo(sec: number) {
    setPlayhead(sec);
  }

  function onError(e: React.SyntheticEvent<HTMLVideoElement>) {
    const v = e.currentTarget;
    const err = v.error;
    if (err) {
      // TEST3: MediaError must NOT be silently swallowed.
      diagRef.current.recordError({ code: err.code, message: err.message || `MEDIA_ERR_${err.code}` });
    }
    useStudio.setState({ lastError: `preview error: ${diagRef.current.summary()}` });
  }

  return (
    <div className="preview">
      <div className="preview-stage" style={aspectStyle(project.aspectRatio)}>
        {transitionActive && outgoingSrc && previewSrc ? (
          <>
            <video
              ref={outgoingRef}
              data-testid="transition-outgoing-video"
              src={outgoingSrc}
              className="preview-video preview-video-layer"
              style={videoTransformStyle(outgoingClip, 1)}
              onError={onError}
            />
            <video
              ref={videoRef}
              data-testid="transition-incoming-video"
              src={previewSrc}
              className="preview-video preview-video-layer"
              style={videoTransformStyle(transitionClip, transitionProgress)}
              onLoadedMetadata={() => diagRef.current.record({ type: "loadedmetadata" })}
              onCanPlay={() => diagRef.current.record({ type: "canplay" })}
              onPlay={() => { diagRef.current.record({ type: "play" }); setPlaying(true); }}
              onPause={() => { diagRef.current.record({ type: "pause" }); setPlaying(false); }}
              onError={onError}
              onTimeUpdate={(e) => {
                if (!e.currentTarget.paused && transitionClip) {
                  setPlayhead(timelineTimeForClip(transitionClip, e.currentTarget.currentTime));
                }
              }}
              onEnded={() => setPlaying(false)}
            />
          </>
        ) : asset && previewSrc ? (
          <video
            ref={videoRef}
            src={previewSrc}
            className="preview-video"
            style={videoTransformStyle(clip)}
            onLoadedMetadata={() => diagRef.current.record({ type: "loadedmetadata" })}
            onCanPlay={() => diagRef.current.record({ type: "canplay" })}
            onPlay={() => { diagRef.current.record({ type: "play" }); setPlaying(true); }}
            onPause={() => { diagRef.current.record({ type: "pause" }); setPlaying(false); }}
            onError={onError}
            onTimeUpdate={(e) => {
              if (!e.currentTarget.paused && clip) {
                setPlayhead(timelineTimeForClip(clip, e.currentTarget.currentTime));
              }
            }}
            onEnded={() => setPlaying(false)}
          />
        ) : (
          <div className="preview-placeholder">Import media and select a clip to preview</div>
        )}
        {clip && (
          <div className="preview-overlay">
            {project.tracks
              .filter((t) => t.kind === "text")
              .flatMap((t) => t.captions)
              .filter((c) => playheadSec >= c.start && playheadSec < c.start + c.duration)
              .map((c) => (
                <div key={c.id} className="caption-overlay" style={captionStyle(c)}>
                  {c.text}
                </div>
              ))}
          </div>
        )}
      </div>
      <div className="preview-controls">
        <button onClick={togglePlay}>{playing ? "❚❚" : "►"}</button>
        <input
          type="range"
          min={0}
          max={Math.max(0.1, project.durationSec)}
          step={0.01}
          value={playheadSec}
          onChange={(e) => seekTo(Number(e.target.value))}
        />
        <span className="time">{playheadSec.toFixed(2)}s / {project.durationSec.toFixed(2)}s</span>
      </div>
    </div>
  );
}

type PreviewPlaybackClip = {
  start: number;
  inPoint: number;
  playbackRate?: number;
  audio?: { gainDb: number; muted: boolean };
};

function applyClipAudio(video: HTMLVideoElement | null, clip: PreviewPlaybackClip | undefined, layerGain: number) {
  if (!video || !clip) return;
  const audio = clip.audio ?? { gainDb: 0, muted: false };
  video.muted = audio.muted;
  const base = Math.pow(10, audio.gainDb / 20);
  video.volume = Math.max(0, Math.min(1, base * layerGain));
}

export function sourceTimeForClip(clip: { start: number; inPoint: number; playbackRate?: number }, playheadSec: number): number {
  return clip.inPoint + (playheadSec - clip.start) * (clip.playbackRate ?? 1);
}

export function timelineTimeForClip(clip: { start: number; inPoint: number; playbackRate?: number }, sourceTimeSec: number): number {
  return clip.start + (sourceTimeSec - clip.inPoint) / (clip.playbackRate ?? 1);
}

function applyClipPlaybackRate(video: HTMLVideoElement | null, clip: PreviewPlaybackClip | undefined) {
  if (!video || !clip) return;
  video.playbackRate = clip.playbackRate ?? 1;
}

function syncVideoTime(video: HTMLVideoElement | null, clip: PreviewPlaybackClip | undefined, playheadSec: number) {
  if (!video || !clip) return;
  const local = sourceTimeForClip(clip, playheadSec);
  if (Math.abs(video.currentTime - local) <= 0.2) return;
  try { video.currentTime = Math.max(0, local); } catch { /* metadata not ready */ }
}

function aspectStyle(ratio: string): React.CSSProperties {
  const [w, h] = ratio.split("x").map(Number);
  const ar = w / h;
  // Fit within the stage.
  return { aspectRatio: String(ar), maxHeight: "100%", maxWidth: "100%" };
}

function videoTransformStyle(clip?: { transform?: { x: number; y: number; scale: number; opacity: number }; effects?: { brightness: number; contrast: number; saturation: number } }, layerOpacity = 1): React.CSSProperties {
  const t = clip?.transform ?? { x: 0, y: 0, scale: 1, opacity: 1 };
  const e = clip?.effects ?? { brightness: 0, contrast: 1, saturation: 1 };
  return {
    transform: `translate(${t.x * 50}%, ${t.y * 50}%) scale(${t.scale})`,
    transformOrigin: "center center",
    opacity: t.opacity * layerOpacity,
    filter: `brightness(${Math.max(0, 1 + e.brightness)}) contrast(${e.contrast}) saturate(${e.saturation})`,
  };
}

function captionStyle(c: { style?: { x: number; y: number; fontSizePx: number; color: string; backgroundColor: string; backgroundOpacity: number } }): React.CSSProperties {
  const s = c.style ?? { x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.6 };
  return {
    position: "absolute",
    left: `${s.x * 100}%`,
    top: `${s.y * 100}%`,
    transform: "translate(-50%, -50%)",
    fontSize: `${s.fontSizePx}px`,
    color: s.color,
    background: hexWithAlpha(s.backgroundColor, s.backgroundOpacity),
    padding: "0.2em 0.5em",
    borderRadius: 6,
    whiteSpace: "pre-wrap",
  };
}

function hexWithAlpha(hex: string, alpha: number): string {
  const a = Math.round(alpha * 255).toString(16).padStart(2, "0");
  return `${hex}${a}`;
}
