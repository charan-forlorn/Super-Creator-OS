import { useRef } from "react";
import { useStudio } from "../store";
import { pxToSec, collectSnapPoints, snap, clamp } from "@haios/timeline";

const PX_PER_SEC_BASE = 80;

export function Timeline() {
  const {
    project, selectedClipId, selectClip, playheadSec, setPlayhead,
    zoom, setZoom, scrollSec, setScroll, snapInterval,
    moveSelected, trimSelected, splitSelected, deleteSelected, duplicateSelected,
  } = useStudio();
  const dragRef = useRef<{ clipId: string; mode: "move" | "trim-l" | "trim-r"; startX: number; startVal: number } | null>(null);

  const pxPerSec = PX_PER_SEC_BASE * zoom;
  const totalSec = Math.max(project.durationSec, 10) + 5;
  const width = totalSec * pxPerSec;

  function onClipMouseDown(ev: React.MouseEvent, clip: { id: string; start: number }, mode: "move" | "trim-l" | "trim-r") {
    ev.stopPropagation();
    selectClip(clip.id);
    dragRef.current = { clipId: clip.id, mode, startX: ev.clientX, startVal: clip.start };
  }

  function onMouseMove(ev: React.MouseEvent) {
    const d = dragRef.current;
    if (!d) return;
    const dxSec = (ev.clientX - d.startX) / pxPerSec;
    const full = project;
    const points = collectSnapPoints(full, { pxPerSecBase: PX_PER_SEC_BASE, zoom, scrollSec, playheadSec, snapInterval });
    if (d.mode === "move") {
      let ns = d.startVal + dxSec;
      const snapped = snap(ns, points, 0.25 / zoom);
      if (snapped.snapped) ns = snapped.value;
      moveSelected(Math.max(0, ns));
    } else if (d.mode === "trim-l") {
      const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === d.clipId)!;
      let nip = clip.inPoint + dxSec;
      const snapped = snap(clip.inPoint + dxSec, [0, ...points], 0.25 / zoom);
      if (snapped.snapped) nip = snapped.value;
      trimSelected(clamp(nip, 0, clip.inPoint + clip.duration - 0.1));
    } else {
      const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === d.clipId)!;
      const rightEdge = clip.start + clip.duration;
      let newEnd = rightEdge + dxSec;
      const snapped = snap(newEnd, points, 0.25 / zoom);
      if (snapped.snapped) newEnd = snapped.value;
      const span = newEnd - clip.start;
      if (span > 0.1) trimSelected(undefined, clip.inPoint + span);
    }
  }

  function onMouseUp() {
    dragRef.current = null;
  }

  function onTrackClick(ev: React.MouseEvent) {
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const sec = clamp(pxToSec({ pxPerSecBase: PX_PER_SEC_BASE, zoom, scrollSec, playheadSec, snapInterval }, ev.clientX - rect.left), 0, totalSec);
    selectClip(null);
    setPlayhead(sec);
  }

  return (
    <div className="timeline">
      <div className="timeline-toolbar">
        <button onClick={deleteSelected} title="Delete">🗑</button>
        <button onClick={duplicateSelected} title="Duplicate">⎘</button>
        <button onClick={() => selectedClipId && splitSelected(0.5)} title="Split at mid">✂</button>
        <div className="spacer" />
        <span>Zoom</span>
        <input type="range" min={0.25} max={4} step={0.25} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} />
        <button onClick={() => setZoom(zoom / 1.25)}>−</button>
        <button onClick={() => setZoom(zoom * 1.25)}>+</button>
      </div>
      <div
        className="timeline-scroll"
        onScroll={(e) => setScroll((e.currentTarget.scrollLeft) / pxPerSec)}
      >
        <div className="timeline-inner" style={{ width }} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}>
          {/* ruler */}
          <div className="timeline-ruler">
            {Array.from({ length: Math.ceil(totalSec) + 1 }).map((_, i) => (
              <div key={i} className="ruler-tick" style={{ left: i * pxPerSec }}>
                {i}s
              </div>
            ))}
            <div className="playhead" style={{ left: playheadSec * pxPerSec }} />
          </div>
          {project.tracks.map((track) => (
            <div key={track.id} className={`track track-${track.kind}`} onClick={onTrackClick}>
              <div className="track-label">{track.kind}</div>
              <div className="track-lane">
                {track.clips.map((clip) => (
                  <ClipView
                    key={clip.id}
                    clip={clip}
                    pxPerSec={pxPerSec}
                    selected={clip.id === selectedClipId}
                    onSelect={() => selectClip(clip.id)}
                    onMouseDownMove={(e) => onClipMouseDown(e, clip, "move")}
                    onMouseDownTrimL={(e) => onClipMouseDown(e, clip, "trim-l")}
                    onMouseDownTrimR={(e) => onClipMouseDown(e, clip, "trim-r")}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ClipView({
  clip, pxPerSec, selected, onSelect, onMouseDownMove, onMouseDownTrimL, onMouseDownTrimR,
}: {
  clip: { id: string; start: number; duration: number; inPoint: number };
  pxPerSec: number;
  selected: boolean;
  onSelect: () => void;
  onMouseDownMove: (e: React.MouseEvent) => void;
  onMouseDownTrimL: (e: React.MouseEvent) => void;
  onMouseDownTrimR: (e: React.MouseEvent) => void;
}) {
  const left = clip.start * pxPerSec;
  const w = Math.max(8, clip.duration * pxPerSec);
  return (
    <div
      className={`clip ${selected ? "selected" : ""}`}
      style={{ left, width: w }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onMouseDown={onMouseDownMove}
    >
      <div className="clip-trim trim-l" onMouseDown={onMouseDownTrimL} />
      <div className="clip-label">in {clip.inPoint.toFixed(1)}</div>
      <div className="clip-trim trim-r" onMouseDown={onMouseDownTrimR} />
    </div>
  );
}
