import { useStudio } from "../store";

export function Inspector() {
  const { project, selectedClipId, moveSelected, trimSelected, setSelectedAudio, setSelectedTransform, changeAspect } = useStudio();
  const clip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === selectedClipId);
  const transform = clip?.transform ?? { scale: 1, x: 0, y: 0, opacity: 1 };

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
          <div className="panel-subhead">Transform</div>
          <TransformField testId="transform-scale" label="Scale" value={transform.scale} min={0.1} max={4} step={0.05}
            onChange={(value) => setSelectedTransform(value, transform.x, transform.y, transform.opacity)} />
          <TransformField testId="transform-x" label="Position X" value={transform.x} min={-1} max={1} step={0.05}
            onChange={(value) => setSelectedTransform(transform.scale, value, transform.y, transform.opacity)} />
          <TransformField testId="transform-y" label="Position Y" value={transform.y} min={-1} max={1} step={0.05}
            onChange={(value) => setSelectedTransform(transform.scale, transform.x, value, transform.opacity)} />
          <TransformField testId="transform-opacity" label="Opacity" value={transform.opacity} min={0} max={1} step={0.05}
            onChange={(value) => setSelectedTransform(transform.scale, transform.x, transform.y, value)} />
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

function TransformField({ testId, label, value, min, max, step, onChange }: {
  testId: string; label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void;
}) {
  return (
    <div className="inspector-row">
      <label>{label}</label>
      <input data-testid={testId} type="number" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
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
