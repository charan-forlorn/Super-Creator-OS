import { useEffect, useMemo, useRef, type CSSProperties, type SyntheticEvent } from "react";
import { compileCompositionPlan } from "@haios/project-model";
import { useStudio } from "../store";
import { resolvePreviewSource } from "../mediaUrl";
import { PlaybackDiagnostics } from "../previewDiagnostics";
import {
  compilePreviewFrame,
  type PreviewAudioEntry,
  type PreviewFrame,
  type PreviewVisualClip,
} from "../previewComposition";

export function Preview() {
  const { project, playheadSec, setPlayhead, previewProxies, transportRate, setTransportRate, toggleTransport } = useStudio();
  const diagRef = useRef(new PlaybackDiagnostics());
  const plan = useMemo(() => compileCompositionPlan(project), [project]);
  const frame = useMemo(() => compilePreviewFrame(plan, playheadSec), [plan, playheadSec]);
  let driverClipId: string | undefined;
  for (let i = frame.visualLayers.length - 1; i >= 0 && !driverClipId; i -= 1) {
    for (let j = frame.visualLayers[i].clips.length - 1; j >= 0; j -= 1) {
      const candidate = frame.visualLayers[i].clips[j];
      if (candidate.asset.kind === "video") { driverClipId = candidate.clip.id; break; }
    }
  }

  useEffect(() => {
    if (transportRate !== 1 || driverClipId) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsed = Math.max(0, (now - last) / 1000);
      last = now;
      const state = useStudio.getState();
      if (state.transportRate !== 1) return;
      const next = Math.min(state.project.durationSec, state.playheadSec + elapsed);
      state.setPlayhead(next);
      if (next >= state.project.durationSec) state.setTransportRate(0);
    }, 33);
    return () => window.clearInterval(timer);
  }, [transportRate, driverClipId]);

  useEffect(() => {
    if (transportRate !== -1) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsed = Math.max(0, (now - last) / 1000);
      last = now;
      const state = useStudio.getState();
      if (state.transportRate !== -1) return;
      const next = Math.max(0, state.playheadSec - elapsed);
      state.setPlayhead(next);
      if (next <= 0) state.setTransportRate(0);
    }, 33);
    return () => window.clearInterval(timer);
  }, [transportRate]);

  function onMediaError(e: SyntheticEvent<HTMLMediaElement>) {
    const err = e.currentTarget.error;
    if (err) diagRef.current.recordError({ code: err.code, message: err.message || `MEDIA_ERR_${err.code}` });
    useStudio.setState({ lastError: `preview error: ${diagRef.current.summary()}` });
  }

  return (
    <div className="preview">
      <PreviewCompositionStage
        frame={frame}
        aspectRatio={project.aspectRatio}
        previewProxies={previewProxies}
        transportRate={transportRate}
        projectDuration={project.durationSec}
        driverClipId={driverClipId}
        setPlayhead={setPlayhead}
        setTransportRate={setTransportRate}
        diag={diagRef.current}
        onMediaError={onMediaError}
      />
      <div className="preview-controls">
        <button data-testid="transport-reverse" onClick={() => setTransportRate(-1)} title="Reverse (J)">J</button>
        <button data-testid="transport-stop" onClick={() => setTransportRate(0)} title="Stop (K)">K</button>
        <button data-testid="transport-play-toggle" data-transport-rate={transportRate} onClick={toggleTransport} title="Play/Pause (Space)">
          {transportRate === 1 ? "❚❚" : transportRate === -1 ? "◀" : "►"}
        </button>
        <button data-testid="transport-forward" onClick={() => setTransportRate(1)} title="Forward (L)">L</button>
        <input
          data-testid="transport-seek"
          type="range"
          min={0}
          max={Math.max(0.1, project.durationSec)}
          step={0.01}
          value={playheadSec}
          onChange={(e) => setPlayhead(Number(e.target.value))}
        />
        <span className="time">{playheadSec.toFixed(2)}s / {project.durationSec.toFixed(2)}s</span>
      </div>
    </div>
  );
}

export interface PreviewCompositionStageProps {
  frame: PreviewFrame;
  aspectRatio: string;
  previewProxies: Record<string, string>;
  transportRate: -1 | 0 | 1;
  projectDuration: number;
  driverClipId?: string;
  setPlayhead: (sec: number) => void;
  setTransportRate: (rate: -1 | 0 | 1) => void;
  diag?: PlaybackDiagnostics;
  onMediaError?: (e: SyntheticEvent<HTMLMediaElement>) => void;
}

export function PreviewCompositionStage(props: PreviewCompositionStageProps) {
  const diagnostics = props.diag ?? new PlaybackDiagnostics();
  const onMediaError = props.onMediaError ?? (() => undefined);
  return (
    <>
      <div className="preview-stage" style={aspectStyle(props.aspectRatio)}>
        {props.frame.visualLayers.map((layer) => (
          <div
            key={layer.trackId}
            className="preview-layer"
            data-preview-layer={layer.trackId}
            style={{ zIndex: layer.zIndex }}
          >
            {layer.clips.map((entry) => (
              <PreviewVisualMedia
                key={entry.clip.id}
                entry={entry}
                previewProxies={props.previewProxies}
                transportRate={props.transportRate}
                drivePlayhead={entry.clip.id === props.driverClipId}
                projectDuration={props.projectDuration}
                setPlayhead={props.setPlayhead}
                setTransportRate={props.setTransportRate}
                diag={diagnostics}
                onMediaError={onMediaError}
              />
            ))}
          </div>
        ))}
        {props.frame.captions.map((entry) => (
          <div
            key={entry.caption.id}
            className="caption-overlay"
            data-preview-caption={entry.caption.id}
            style={{ ...captionStyle(entry.caption), zIndex: entry.zIndex }}
          >
            {entry.caption.text}
          </div>
        ))}
        {props.frame.visualLayers.length === 0 && props.frame.captions.length === 0 && (
          <div className="preview-placeholder">Import media and select a clip to preview</div>
        )}
      </div>
      <div className="preview-audio-runtime" aria-hidden="true">
        {props.frame.audio.map((entry) => (
          <PreviewAudioMedia
            key={`${entry.trackId}:${entry.clip.clipId}`}
            entry={entry}
            previewProxies={props.previewProxies}
            transportRate={props.transportRate}
            onMediaError={onMediaError}
          />
        ))}
      </div>
    </>
  );
}

function PreviewVisualMedia(props: {
  entry: PreviewVisualClip;
  previewProxies: Record<string, string>;
  transportRate: -1 | 0 | 1;
  drivePlayhead: boolean;
  projectDuration: number;
  setPlayhead: (sec: number) => void;
  setTransportRate: (rate: -1 | 0 | 1) => void;
  diag: PlaybackDiagnostics;
  onMediaError: (e: SyntheticEvent<HTMLMediaElement>) => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { entry } = props;
  const src = resolvePreviewSource({
    sourcePath: entry.asset.sourcePath,
    proxyPath: props.previewProxies[entry.asset.id],
  });

  useEffect(() => {
    const video = videoRef.current;
    if (!video || entry.asset.kind !== "video") return;
    video.playbackRate = entry.clip.playbackRate ?? 1;
    if (Math.abs(video.currentTime - entry.sourceTimeSec) > 0.2) {
      try { video.currentTime = Math.max(0, entry.sourceTimeSec); } catch { /* metadata not ready */ }
    }
  }, [entry.asset.kind, entry.clip.id, entry.clip.playbackRate, entry.sourceTimeSec]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || entry.asset.kind !== "video") return;
    if (props.transportRate === 1) video.play().catch(() => props.setTransportRate(0));
    else video.pause();
  }, [props.transportRate, entry.asset.kind, entry.clip.id, props.setTransportRate]);

  if (entry.asset.kind === "image") {
    return (
      <img
        data-preview-visual={entry.clip.id}
        src={src}
        className="preview-video preview-video-layer"
        style={videoTransformStyle(entry.clip, entry.opacity)}
        alt=""
      />
    );
  }
  return (
    <video
      ref={videoRef}
      muted
      data-preview-visual={entry.clip.id}
      src={src}
      className="preview-video preview-video-layer"
      style={videoTransformStyle(entry.clip, entry.opacity)}
      onLoadedMetadata={() => props.diag.record({ type: "loadedmetadata" })}
      onCanPlay={() => props.diag.record({ type: "canplay" })}
      onPlay={() => props.diag.record({ type: "play" })}
      onPause={() => props.diag.record({ type: "pause" })}
      onError={props.onMediaError}
      onTimeUpdate={(e) => {
        if (props.drivePlayhead && !e.currentTarget.paused) {
          props.setPlayhead(timelineTimeForClip(entry.clip, e.currentTarget.currentTime));
        }
      }}
      onEnded={() => {
        if (!props.drivePlayhead) return;
        const end = Math.min(props.projectDuration, entry.clip.start + entry.clip.duration);
        props.setPlayhead(end);
        if (end >= props.projectDuration) props.setTransportRate(0);
      }}
    />
  );
}

function PreviewAudioMedia(props: {
  entry: PreviewAudioEntry;
  previewProxies: Record<string, string>;
  transportRate: -1 | 0 | 1;
  onMediaError: (e: SyntheticEvent<HTMLMediaElement>) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const assetId = props.entry.clip.assetId;
  const src = resolvePreviewSource({
    sourcePath: props.entry.clip.sourcePath,
    proxyPath: props.previewProxies[assetId],
  });

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = props.entry.clip.playbackRate;
    audio.volume = Math.max(0, Math.min(1, Math.pow(10, props.entry.clip.gainDb / 20) * props.entry.gainScale));
    if (Math.abs(audio.currentTime - props.entry.sourceTimeSec) > 0.2) {
      try { audio.currentTime = Math.max(0, props.entry.sourceTimeSec); } catch { /* metadata not ready */ }
    }
  }, [props.entry.clip.clipId, props.entry.clip.playbackRate, props.entry.clip.gainDb, props.entry.gainScale, props.entry.sourceTimeSec]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (props.transportRate === 1) audio.play().catch(() => undefined);
    else audio.pause();
  }, [props.transportRate, props.entry.clip.clipId]);

  return (
    <audio
      ref={audioRef}
      data-preview-audio={props.entry.clip.clipId}
      src={src}
      onError={props.onMediaError}
    />
  );
}

export function sourceTimeForClip(clip: { start: number; inPoint: number; playbackRate?: number }, playheadSec: number): number {
  return clip.inPoint + (playheadSec - clip.start) * (clip.playbackRate ?? 1);
}

export function timelineTimeForClip(clip: { start: number; inPoint: number; playbackRate?: number }, sourceTimeSec: number): number {
  return clip.start + (sourceTimeSec - clip.inPoint) / (clip.playbackRate ?? 1);
}

function aspectStyle(ratio: string): CSSProperties {
  const [w, h] = ratio.split("x").map(Number);
  return { aspectRatio: String(w / h), maxHeight: "100%", maxWidth: "100%" };
}

function videoTransformStyle(
  clip?: {
    transform?: { x: number; y: number; scale: number; opacity: number };
    effects?: { brightness: number; contrast: number; saturation: number };
  },
  layerOpacity = 1,
): CSSProperties {
  const t = clip?.transform ?? { x: 0, y: 0, scale: 1, opacity: 1 };
  const e = clip?.effects ?? { brightness: 0, contrast: 1, saturation: 1 };
  return {
    transform: `translate(${t.x * 50}%, ${t.y * 50}%) scale(${t.scale})`,
    transformOrigin: "center center",
    opacity: t.opacity * layerOpacity,
    filter: `brightness(${Math.max(0, 1 + e.brightness)}) contrast(${e.contrast}) saturate(${e.saturation})`,
  };
}

function captionStyle(c: {
  style?: {
    x: number;
    y: number;
    fontSizePx: number;
    color: string;
    backgroundColor: string;
    backgroundOpacity: number;
  };
}): CSSProperties {
  const s = c.style ?? {
    x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF",
    backgroundColor: "#000000", backgroundOpacity: 0.6,
  };
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
