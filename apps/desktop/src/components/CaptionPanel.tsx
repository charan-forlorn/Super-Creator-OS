import { useState } from "react";
import { useStudio } from "../store";

export function CaptionPanel() {
  const { project, playheadSec, placeCaption, removeCaption } = useStudio();
  const [text, setText] = useState("");
  const [duration, setDuration] = useState(3);
  const captions = project.tracks
    .filter((t) => t.kind === "text")
    .flatMap((t) => t.captions.map((caption) => ({ caption, trackId: t.id })))
    .sort((a, b) => a.caption.start - b.caption.start);

  function add() {
    const value = text.trim();
    if (!value || !(duration > 0)) return;
    if (placeCaption(value, playheadSec, duration)) setText("");
  }

  return (
    <div className="caption-workspace" data-testid="caption-workspace">
      <div className="rail-section-title">Captions</div>
      <textarea
        data-testid="caption-text"
        value={text}
        placeholder="Add caption at playhead"
        onChange={(e) => setText(e.target.value)}
      />
      <div className="caption-controls">
        <label>
          Duration
          <input
            data-testid="caption-duration"
            type="number"
            min={0.1}
            step={0.1}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </label>
        <button data-testid="caption-add" onClick={add} disabled={!text.trim() || !(duration > 0)}>
          Add
        </button>
      </div>
      <div className="caption-list" data-testid="caption-list">
        {captions.length === 0 && <div className="empty-hint">No captions yet.</div>}
        {captions.map(({ caption, trackId }) => (
          <div className="caption-row" data-testid={`caption-row-${caption.id}`} key={caption.id}>
            <div>
              <div className="caption-row-text">{caption.text}</div>
              <div className="media-sub">{caption.start.toFixed(1)}s · {caption.duration.toFixed(1)}s</div>
            </div>
            <button
              data-testid={`caption-delete-${caption.id}`}
              onClick={() => removeCaption(caption.id, trackId)}
              aria-label={`Delete caption ${caption.id}`}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
