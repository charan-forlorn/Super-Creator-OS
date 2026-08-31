import { useEffect, useRef, useState } from "react";
import { useStudio } from "../store";
import { resolvePreviewSource } from "../mediaUrl";
import { PlaybackDiagnostics } from "../previewDiagnostics";

export function Preview() {
  const { project, playheadSec, setPlayhead, previewProxies } = useStudio();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const diagRef = useRef<PlaybackDiagnostics>(new PlaybackDiagnostics());

  // Resolve the clip under the playhead on the first video track.
  const clip = project.tracks
    .filter((t) => t.kind === "video")
    .flatMap((t) => t.clips)
    .find((c) => playheadSec >= c.start && playheadSec < c.start + c.duration);

  const asset = clip ? project.assets.find((a) => a.id === clip.assetId) : undefined;

  // ROOT_CAUSE_2 FIX: never assign a raw Windows filesystem path to video.src.
  // Route every media source through the centralized Tauri-safe resolver.
  const previewSrc = asset ? resolvePreviewSource({ sourcePath: asset.sourcePath, proxyPath: previewProxies[asset.id] }) : undefined;

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !clip) return;
    const audio = clip.audio ?? { gainDb: 0, muted: false };
    v.muted = audio.muted;
    v.volume = Math.max(0, Math.min(1, Math.pow(10, audio.gainDb / 20)));
  }, [clip?.id, clip?.audio?.gainDb, clip?.audio?.muted]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !asset) return;
    const local = playheadSec - (clip?.start ?? 0) + (clip?.inPoint ?? 0);
    if (Math.abs(v.currentTime - local) > 0.2) {
      try {
        v.currentTime = Math.max(0, local);
      } catch {
        /* seeking before metadata ready */
      }
    }
  }, [playheadSec, asset, clip]);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      v.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    } else {
      v.pause();
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
        {asset && previewSrc ? (
          <video
            ref={videoRef}
            src={previewSrc}
            className="preview-video"
            onLoadedMetadata={() => diagRef.current.record({ type: "loadedmetadata" })}
            onCanPlay={() => diagRef.current.record({ type: "canplay" })}
            onPlay={() => { diagRef.current.record({ type: "play" }); setPlaying(true); }}
            onPause={() => { diagRef.current.record({ type: "pause" }); setPlaying(false); }}
            onError={onError}
            onTimeUpdate={(e) => {
              const t = e.currentTarget.currentTime;
              if (!e.currentTarget.paused) {
                // keep playhead synced while playing
                const next = (clip?.start ?? 0) - (clip?.inPoint ?? 0) + t;
                setPlayhead(next);
              }
            }}
            onEnded={() => setPlaying(false)}
          />
        ) : (
          <div className="preview-placeholder">Import media and select a clip to preview</div>
        )}
        {clip && (
          <div className="preview-overlay" style={overlayStyle(clip)}>
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

function aspectStyle(ratio: string): React.CSSProperties {
  const [w, h] = ratio.split("x").map(Number);
  const ar = w / h;
  // Fit within the stage.
  return { aspectRatio: String(ar), maxHeight: "100%", maxWidth: "100%" };
}

function overlayStyle(clip: { transform?: { x: number; y: number; scale: number; opacity: number } }): React.CSSProperties {
  const t = clip.transform ?? { x: 0, y: 0, scale: 1, opacity: 1 };
  return {
    transform: `translate(${t.x * 100}%, ${t.y * 100}%) scale(${t.scale})`,
    opacity: t.opacity,
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
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
