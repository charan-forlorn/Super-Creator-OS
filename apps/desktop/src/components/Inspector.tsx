import { useStudio } from "../store";

export function Inspector() {
  const { project, selectedClipId, moveSelected, trimSelected, setSelectedAudio, changeAspect } = useStudio();
  const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === selectedClipId);

  return (
    <div className="panel inspector">
      <div className="panel-head"><span>Inspector</span></div>
      {!clip && <div className="empty-hint">Select a clip to edit its properties.</div>}
      {clip && (
        <div className="inspector-body">
          <Field label="Clip ID" value={clip.id} />
          <Field label="In-point (s)" value={clip.inPoint.toFixed(2)} />
          <Field label="Duration (s)" value={clip.duration.toFixed(2)} />
          <Field label="Start (s)" value={clip.start.toFixed(2)} />
          <div className="inspector-row">
            <label>Move start</label>
            <input
              type="number"
              step={0.1}
              defaultValue={clip.start}
              onBlur={(e) => moveSelected(Number(e.target.value))}
            />
          </div>
          <div className="inspector-row">
            <label>Trim in-point</label>
            <input
              type="number"
              step={0.1}
              defaultValue={clip.inPoint}
              onBlur={(e) => trimSelected(Number(e.target.value))}
            />
          </div>
          <div className="inspector-row">
            <label>Scale</label>
            <span>{clip.transform?.scale ?? 1}</span>
          </div>
          <div className="inspector-row">
            <label>Gain (dB)</label>
            <input
              data-testid="audio-gain"
              type="number" min={-60} max={0} step={1}
              value={clip.audio?.gainDb ?? 0}
              onChange={(e) => setSelectedAudio(Number(e.target.value), clip.audio?.muted ?? false)}
            />
          </div>
          <div className="inspector-row">
            <label>Mute</label>
            <input
              data-testid="audio-muted"
              type="checkbox"
              checked={clip.audio?.muted ?? false}
              onChange={(e) => setSelectedAudio(clip.audio?.gainDb ?? 0, e.target.checked)}
            />
          </div>
        </div>
      )}
      <div className="inspector-section">
        <div className="panel-subhead">Project</div>
        <div className="inspector-row">
          <label>Aspect ratio</label>
          <select value={project.aspectRatio} onChange={(e) => changeAspect(e.target.value as any)}>
            <option value="1920x1080">1920×1080 (Landscape)</option>
            <option value="1080x1920">1080×1920 (Vertical)</option>
            <option value="1080x1080">1080×1080 (Square)</option>
          </select>
        </div>
        <Field label="Schema v" value={String(project.schemaVersion)} />
        <Field label="Duration" value={`${project.durationSec.toFixed(2)}s`} />
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="inspector-row">
      <label>{label}</label>
      <span>{value}</span>
    </div>
  );
}
