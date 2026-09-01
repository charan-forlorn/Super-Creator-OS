import { useRef, useState } from "react";
import { useStudio } from "../store";
import { pxToSec, collectSnapCandidates, findMagneticSnap, clamp, type SnapTarget } from "@haios/timeline";

const PX_PER_SEC_BASE = 80;

export function Timeline() {
  const {
    project,
    selectedClipId,
    selectedClipIds,
    selectClip,
    toggleClipSelection,
    setClipSelection,
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
    rippleDeleteSelected,
    rippleTrimSelected,
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
  const marqueeRef = useRef<{
    startClientX: number; startClientY: number;
    currentClientX: number; currentClientY: number;
    additive: boolean; moved: boolean; innerLeft: number; innerTop: number;
  } | null>(null);
  const suppressTrackClickRef = useRef(false);
  const [marqueePreview, setMarqueePreview] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [movePreview, setMovePreview] = useState<{ ids: string[]; delta: number } | null>(null);
  const [rippleTrimEnabled, setRippleTrimEnabled] = useState(false);
  const [ripplePreview, setRipplePreview] = useState<{ clipId: string; duration: number; sourceEnd?: number; inPoint?: number } | null>(null);
  const [snapEnabled, setSnapEnabled] = useState(false);
  const [snapGuide, setSnapGuide] = useState<{ sec: number; target: SnapTarget } | null>(null);

  const pxPerSec = PX_PER_SEC_BASE * zoom;
  const totalSec = Math.max(project.durationSec, 10) + 5;
  const width = totalSec * pxPerSec;

  function onClipMouseDown(
    ev: React.MouseEvent,
    clip: { id: string; start: number; inPoint: number; duration: number; playbackRate?: number },
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
      if (c) startVals[id] = mode === "trim-l" ? c.inPoint : mode === "trim-r" ? c.duration : c.start;
    }
    dragRef.current = { mode, startX: ev.clientX, startVals };
    groupPreviewRef.current = null;
    setMovePreview(null);
    setRipplePreview(null);
    setSnapGuide(null);
    ev.preventDefault();
  }

  function onMouseMove(ev: React.MouseEvent) {
    const marquee = marqueeRef.current;
    if (marquee) {
      marquee.currentClientX = ev.clientX;
      marquee.currentClientY = ev.clientY;
      marquee.moved ||= Math.hypot(ev.clientX - marquee.startClientX, ev.clientY - marquee.startClientY) >= 4;
      const left = Math.min(marquee.startClientX, ev.clientX) - marquee.innerLeft;
      const top = Math.min(marquee.startClientY, ev.clientY) - marquee.innerTop;
      setMarqueePreview({ left, top, width: Math.abs(ev.clientX - marquee.startClientX), height: Math.abs(ev.clientY - marquee.startClientY) });
      ev.preventDefault();
      return;
    }
    const d = dragRef.current;
    if (!d) return;
    const dxSec = (ev.clientX - d.startX) / pxPerSec;
    const targets = Object.keys(d.startVals);
    const snapView = { pxPerSecBase: PX_PER_SEC_BASE, zoom, scrollSec, playheadSec, snapInterval };
    const candidates = snapEnabled && !ev.altKey
      ? collectSnapCandidates(project, snapView, new Set(targets))
      : [];
    if (d.mode === "move") {
      if (targets.length === 0) return;
      const moving = targets.map((id) => project.tracks.flatMap((t) => t.clips).find((c) => c.id === id)).filter((c): c is NonNullable<typeof c> => Boolean(c));
      if (moving.length === 0) return;
      const rawLeft = Math.min(...moving.map((c) => d.startVals[c.id] + dxSec));
      const rawRight = Math.max(...moving.map((c) => d.startVals[c.id] + c.duration + dxSec));
      let delta = dxSec;
      const magnetic = findMagneticSnap([rawLeft, rawRight], candidates, 0.25 / zoom);
      if (magnetic.snapped) {
        delta += magnetic.delta;
        setSnapGuide({ sec: magnetic.guideSec!, target: magnetic.target! });
      } else setSnapGuide(null);
      const minAdjusted = Math.min(...moving.map((c) => d.startVals[c.id] + delta));
      if (minAdjusted < 0) {
        delta -= minAdjusted;
        setSnapGuide(null);
      }
      groupPreviewRef.current = delta;
      setMovePreview({ ids: targets, delta });
      return;
    }

    for (const id of targets) {
      if (d.mode === "trim-l") {
        if (id !== selectedClipId) continue;
        const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === id)!;
        const rate = clip.playbackRate ?? 1;
        const originalSourceEnd = clip.inPoint + clip.duration * rate;
        const maxInPoint = originalSourceEnd - 0.1 * rate;
        const nip = clamp(d.startVals[id] + dxSec * rate, 0, maxInPoint);
        const duration = (originalSourceEnd - nip) / rate;
        setSnapGuide(null);
        setRipplePreview({ clipId: id, duration, inPoint: nip });
      } else {
        if (id !== selectedClipId) continue;
        const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === id)!;
        const baseDuration = d.startVals[id];
        const rightEdge = clip.start + baseDuration;
        let newEnd = rightEdge + dxSec;
        const magnetic = findMagneticSnap([newEnd], candidates, 0.25 / zoom);
        if (magnetic.snapped) {
          newEnd += magnetic.delta;
          setSnapGuide({ sec: magnetic.guideSec!, target: magnetic.target! });
        } else setSnapGuide(null);
        const span = newEnd - clip.start;
        if (span > 0.1) {
          const sourceEnd = clip.inPoint + span * (clip.playbackRate ?? 1);
          setRipplePreview({ clipId: id, duration: span, sourceEnd });
        }
      }
    }
  }

  function onMouseUp() {
    const marquee = marqueeRef.current;
    if (marquee) {
      marqueeRef.current = null;
      setMarqueePreview(null);
      if (marquee.moved) {
        const left = Math.min(marquee.startClientX, marquee.currentClientX);
        const right = Math.max(marquee.startClientX, marquee.currentClientX);
        const top = Math.min(marquee.startClientY, marquee.currentClientY);
        const bottom = Math.max(marquee.startClientY, marquee.currentClientY);
        const ids = Array.from(document.querySelectorAll<HTMLElement>(".track-lane .clip"))
          .filter((el) => { const r = el.getBoundingClientRect(); return r.left < right && r.right > left && r.top < bottom && r.bottom > top; })
          .map((el) => el.dataset.clipId)
          .filter((id): id is string => Boolean(id));
        setClipSelection(ids, marquee.additive);
        suppressTrackClickRef.current = true;
        window.setTimeout(() => { suppressTrackClickRef.current = false; }, 0);
      }
      return;
    }
    const d = dragRef.current;
    dragRef.current = null;
    if (!d) return;
    // Commit a group move (delta) as one atomic undoable unit when multiple clips
    // were dragged, or when a single clip moved with others selected.
    const targets = Object.keys(d.startVals);
    if (d.mode === "move") {
      const delta = groupPreviewRef.current ?? 0;
      if (Math.abs(delta) > 1e-6) {
        if (targets.length > 1) commitGroupMove(delta);
        else if (targets[0]) moveSelected(d.startVals[targets[0]] + delta);
      }
    }
    if (d.mode === "trim-l" && ripplePreview?.inPoint !== undefined) {
      trimSelected(ripplePreview.inPoint);
    }
    if (d.mode === "trim-r" && ripplePreview?.sourceEnd !== undefined) {
      if (rippleTrimEnabled) rippleTrimSelected(undefined, ripplePreview.sourceEnd);
      else trimSelected(undefined, ripplePreview.sourceEnd);
    }
    groupPreviewRef.current = null;
    setMovePreview(null);
    setRipplePreview(null);
    setSnapGuide(null);
  }

  function onLaneMouseDown(ev: React.MouseEvent) {
    if (ev.button !== 0) return;
    const inner = (ev.currentTarget as HTMLElement).closest<HTMLElement>(".timeline-inner");
    if (!inner) return;
    const r = inner.getBoundingClientRect();
    marqueeRef.current = { startClientX: ev.clientX, startClientY: ev.clientY, currentClientX: ev.clientX, currentClientY: ev.clientY, additive: ev.shiftKey || ev.ctrlKey || ev.metaKey, moved: false, innerLeft: r.left, innerTop: r.top };
    setMarqueePreview({ left: ev.clientX - r.left, top: ev.clientY - r.top, width: 0, height: 0 });
  }

  function onTrackClick(ev: React.MouseEvent) {
    if (suppressTrackClickRef.current) return;
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
        <button data-testid="ripple-delete" onClick={rippleDeleteSelected} title="Ripple delete selected (Shift+Del)">Ripple Delete</button>
        <label className="ripple-toggle" title="Ripple downstream clips when trimming the right edge">
          <input type="checkbox" data-testid="ripple-trim-toggle" checked={rippleTrimEnabled} onChange={(e) => setRippleTrimEnabled(e.target.checked)} />
          Ripple Trim
        </label>
        <button onClick={duplicateSelected} title="Duplicate selected (Ctrl+D)">⎘</button>
        <button onClick={() => splitSelected()} title="Split selected at playhead (S)">✂</button>
        <button onClick={selectAllClips} title="Select all (Ctrl+A)">⤢</button>
        <label className="snap-toggle" title="Magnetic snapping (hold Alt to bypass)">
          <input type="checkbox" data-testid="snap-toggle" checked={snapEnabled} onChange={(e) => setSnapEnabled(e.target.checked)} />
          Snap
        </label>
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
          {marqueePreview && (
            <div
              className="timeline-marquee"
              data-testid="timeline-marquee"
              style={{ left: marqueePreview.left, top: marqueePreview.top, width: marqueePreview.width, height: marqueePreview.height }}
            />
          )}
          {snapGuide && (
            <div
              className="snap-guide"
              data-testid="snap-guide"
              data-snap-target={snapGuide.target}
              data-guide-sec={snapGuide.sec}
              style={{ left: 64 + snapGuide.sec * pxPerSec }}
            />
          )}
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
              <div className="track-lane" onMouseDown={onLaneMouseDown}>
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
                    previewStart={movePreview?.ids.includes(clip.id) ? clip.start + movePreview.delta : undefined}
                    previewDuration={ripplePreview?.clipId === clip.id ? ripplePreview.duration : undefined}
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
  previewStart,
  previewDuration,
}: {
  clip: { id: string; start: number; duration: number; inPoint: number };
  trackKind: string;
  pxPerSec: number;
  selected: boolean;
  primary: boolean;
  onMouseDownMove: (e: React.MouseEvent) => void;
  onMouseDownTrimL: (e: React.MouseEvent) => void;
  onMouseDownTrimR: (e: React.MouseEvent) => void;
  previewStart?: number;
  previewDuration?: number;
}) {
  const left = (previewStart ?? clip.start) * pxPerSec;
  const w = Math.max(8, (previewDuration ?? clip.duration) * pxPerSec);
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
