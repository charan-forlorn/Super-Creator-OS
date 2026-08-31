import { useRef } from "react";
import { useStudio } from "../store";
import { pxToSec, collectSnapPoints, snap, clamp } from "@haios/timeline";

const PX_PER_SEC_BASE = 80;

export function Timeline() {
  const {
    project,
    selectedClipId,
    selectedClipIds,
    selectClip,
    toggleClipSelection,
    selectAllClips,
    clearClipSelection,
    playheadSec,
    setPlayhead,
    zoom,
    setZoom,
    scrollSec,
    setScroll,
    snapInterval,
    moveSelected,
    commitGroupMove,
    trimSelected,
    splitSelected,
    deleteSelected,
    duplicateSelected,
  } = useStudio();

  // Drag state. For a group drag we capture the ORIGINAL starts of every selected
  // clip and, on mouse-up, commit a single group move (one undo entry). Live
  // preview updates the primary selection only; the authoritative group shift is
  // applied on commit so undo/redo stays exact.
  const dragRef = useRef<{
    mode: "move" | "trim-l" | "trim-r";
    startX: number;
    startVals: Record<string, number>; // clipId -> start (move) or inPoint (trim)
  } | null>(null);
  const groupPreviewRef = useRef<number | null>(null);

  const pxPerSec = PX_PER_SEC_BASE * zoom;
  const totalSec = Math.max(project.durationSec, 10) + 5;
  const width = totalSec * pxPerSec;

  function onClipMouseDown(
    ev: React.MouseEvent,
    clip: { id: string; start: number; inPoint: number },
    mode: "move" | "trim-l" | "trim-r",
  ) {
    ev.stopPropagation();
    // Mouse-down is the sole selection authority. Keeping selection mutation here
    // lets a drag capture the post-gesture group; click only stops background
    // propagation (otherwise Ctrl-click would toggle twice).
    const extending = ev.shiftKey || ev.ctrlKey || ev.metaKey;
    const wasSelected = selectedClipIds.includes(clip.id);
    const nextSelectedIds = extending
      ? wasSelected
        ? selectedClipIds.filter((id) => id !== clip.id)
        : [...selectedClipIds, clip.id]
      : wasSelected
        ? selectedClipIds
        : [clip.id];
    if (extending) {
      toggleClipSelection(clip.id);
    } else if (!wasSelected) {
      selectClip(clip.id);
    }
    const targets = nextSelectedIds;
    const startVals: Record<string, number> = {};
    for (const id of targets) {
      const c = project.tracks.flatMap((t) => t.clips).find((x) => x.id === id);
      if (c) startVals[id] = mode === "trim-l" ? c.inPoint : c.start;
    }
    dragRef.current = { mode, startX: ev.clientX, startVals };
    groupPreviewRef.current = null;
    ev.preventDefault();
  }

  function onMouseMove(ev: React.MouseEvent) {
    const d = dragRef.current;
    if (!d) return;
    const dxSec = (ev.clientX - d.startX) / pxPerSec;
    const points = collectSnapPoints(project, {
      pxPerSecBase: PX_PER_SEC_BASE,
      zoom,
      scrollSec,
      playheadSec,
      snapInterval,
    });
    const targets = Object.keys(d.startVals);
    if (d.mode === "move") {
      if (targets.length > 1) {
        // A group drag is preview-only until mouse-up. Mutating a primary clip
        // here would create an extra history entry and double-shift it when the
        // atomic batch below commits. Snap the group delta from its primary.
        const primaryId = selectedClipId && d.startVals[selectedClipId] !== undefined
          ? selectedClipId
          : targets[0];
        const base = d.startVals[primaryId];
        let nextStart = base + dxSec;
        const snapped = snap(nextStart, points, 0.25 / zoom);
        if (snapped.snapped) nextStart = snapped.value;
        groupPreviewRef.current = nextStart - base;
        return;
      }

      const id = targets[0];
      if (!id) return;
      const base = d.startVals[id];
      let nextStart = base + dxSec;
      const snapped = snap(nextStart, points, 0.25 / zoom);
      if (snapped.snapped) nextStart = snapped.value;
      moveSelected(Math.max(0, nextStart));
      return;
    }

    for (const id of targets) {
      if (d.mode === "trim-l") {
        if (id !== selectedClipId) continue;
        const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === id)!;
        let nip = clip.inPoint + dxSec;
        const snapped = snap(clip.inPoint + dxSec, [0, ...points], 0.25 / zoom);
        if (snapped.snapped) nip = snapped.value;
        trimSelected(clamp(nip, 0, clip.inPoint + clip.duration - 0.1));
      } else {
        if (id !== selectedClipId) continue;
        const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === id)!;
        const rightEdge = clip.start + clip.duration;
        let newEnd = rightEdge + dxSec;
        const snapped = snap(newEnd, points, 0.25 / zoom);
        if (snapped.snapped) newEnd = snapped.value;
        const span = newEnd - clip.start;
        if (span > 0.1) trimSelected(undefined, clip.inPoint + span);
      }
    }
  }

  function onMouseUp() {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d) return;
    // Commit a group move (delta) as one atomic undoable unit when multiple clips
    // were dragged, or when a single clip moved with others selected.
    const targets = Object.keys(d.startVals);
    if (d.mode === "move" && targets.length > 1) {
      const delta = groupPreviewRef.current ?? 0;
      if (Math.abs(delta) > 1e-6) commitGroupMove(delta);
    }
    groupPreviewRef.current = null;
  }

  function onTrackClick(ev: React.MouseEvent) {
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const sec = clamp(
      pxToSec({ pxPerSecBase: PX_PER_SEC_BASE, zoom, scrollSec, playheadSec, snapInterval }, ev.clientX - rect.left),
      0,
      totalSec,
    );
    // Plain background click clears selection (Shift+click keeps multiselection).
    if (!(ev.shiftKey || ev.ctrlKey || ev.metaKey)) clearClipSelection();
    setPlayhead(sec);
  }

  // Ruler clicks set the playhead WITHOUT clearing selection, so an existing
  // multi-selection can be split at the chosen time through a real GUI gesture.
  function onRulerClick(ev: React.MouseEvent) {
    const rect = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    const sec = clamp(
      pxToSec({ pxPerSecBase: PX_PER_SEC_BASE, zoom, scrollSec, playheadSec, snapInterval }, ev.clientX - rect.left),
      0,
      totalSec,
    );
    setPlayhead(sec);
  }

  return (
    <div className="timeline">
      <div className="timeline-toolbar">
        <button onClick={deleteSelected} title="Delete selected (Del)">🗑</button>
        <button onClick={duplicateSelected} title="Duplicate selected (Ctrl+D)">⎘</button>
        <button onClick={() => splitSelected()} title="Split selected at playhead (S)">✂</button>
        <button onClick={selectAllClips} title="Select all (Ctrl+A)">⤢</button>
        <div className="spacer" />
        <span>Zoom</span>
        <input
          type="range"
          min={0.25}
          max={4}
          step={0.25}
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
        />
        <button onClick={() => setZoom(zoom / 1.25)}>−</button>
        <button onClick={() => setZoom(zoom * 1.25)}>+</button>
        <span className="sel-count" data-testid="selection-count">{selectedClipIds.length} selected</span>
      </div>
      <div
        className="timeline-scroll"
        onScroll={(e) => setScroll(e.currentTarget.scrollLeft / pxPerSec)}
      >
        <div
          className="timeline-inner"
          style={{ width }}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        >
          <div className="timeline-ruler">
            <div className="ruler-label" />
            <div className="ruler-lane" onClick={onRulerClick}>
              {Array.from({ length: Math.ceil(totalSec) + 1 }).map((_, i) => (
                <div key={i} className="ruler-tick" style={{ left: i * pxPerSec }}>
                  {i}s
                </div>
              ))}
              <div className="playhead" style={{ left: playheadSec * pxPerSec }} />
            </div>
          </div>
          {project.tracks.map((track) => (
            <div key={track.id} className={`track track-${track.kind}`} onClick={onTrackClick}>
              <div className="track-label">{track.kind}</div>
              <div className="track-lane">
                {track.clips.map((clip) => (
                  <ClipView
                    key={clip.id}
                    clip={clip}
                    trackKind={track.kind}
                    pxPerSec={pxPerSec}
                    selected={selectedClipIds.includes(clip.id)}
                    primary={clip.id === selectedClipId}
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
  clip,
  trackKind,
  pxPerSec,
  selected,
  primary,
  onMouseDownMove,
  onMouseDownTrimL,
  onMouseDownTrimR,
}: {
  clip: { id: string; start: number; duration: number; inPoint: number };
  trackKind: string;
  pxPerSec: number;
  selected: boolean;
  primary: boolean;
  onMouseDownMove: (e: React.MouseEvent) => void;
  onMouseDownTrimL: (e: React.MouseEvent) => void;
  onMouseDownTrimR: (e: React.MouseEvent) => void;
}) {
  const left = clip.start * pxPerSec;
  const w = Math.max(8, clip.duration * pxPerSec);
  const cls = ["clip", selected ? "selected" : "", primary ? "primary" : ""].filter(Boolean).join(" ");
  return (
    <div
      className={cls}
      data-testid={`clip-${clip.id}`}
      data-clip-id={clip.id}
      data-selected={selected ? "true" : "false"}
      data-primary={primary ? "true" : "false"}
      data-start={clip.start}
      data-duration={clip.duration}
      data-track={trackKind}
      style={{ left, width: w }}
      onClick={(e) => {
        // Selection is handled once in onMouseDown; prevent the track's
        // background-click handler from clearing it after a clip gesture.
        e.stopPropagation();
      }}
      onMouseDown={onMouseDownMove}
    >
      <div className="clip-trim trim-l" onMouseDown={onMouseDownTrimL} />
      <div className="clip-label">in {clip.inPoint.toFixed(1)}</div>
      <div className="clip-trim trim-r" onMouseDown={onMouseDownTrimR} />
    </div>
  );
}
