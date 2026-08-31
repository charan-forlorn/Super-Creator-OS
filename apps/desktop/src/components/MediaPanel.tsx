import { useEffect, useMemo, useState } from "react";
import { useStudio } from "../store";
import {
  selectMediaFile,
  probeMedia,
  ensureThumbnail,
  ensurePreviewProxy,
  ensureWaveform,
  type MediaProbe,
} from "../bridge";
import { previewNeedsProxy } from "@haios/media-engine";
import { CaptionPanel } from "./CaptionPanel";
import { previewUrlForPath } from "../mediaUrl";
import { analyzeMediaSource, mediaAnalysisQueue } from "../mediaAnalysis";

const analysisDeps = {
  probeMedia,
  ensureThumbnail,
  ensurePreviewProxy,
  ensureWaveform,
  previewNeedsProxy: (p: { kind: string; videoCodec: string | null; audioCodec: string | null }) =>
    previewNeedsProxy({ kind: p.kind as "video" | "audio" | "image", videoCodec: p.videoCodec, audioCodec: p.audioCodec }),
};

function scheduleAnalysis(assetId: string, sourcePath: string, initialProbe?: MediaProbe): void {
  const state = useStudio.getState();
  const existing = state.mediaAnalysis[assetId];
  if (existing?.sourcePath === sourcePath && ["queued", "analyzing", "ready", "missing"].includes(existing.status)) {
    return;
  }
  state.setMediaAnalysis(assetId, { sourcePath, status: "queued", probe: initialProbe });
  void mediaAnalysisQueue.enqueue(async () => {
    const before = useStudio.getState().mediaAnalysis[assetId];
    if (!before || before.sourcePath !== sourcePath) return;
    useStudio.getState().setMediaAnalysis(assetId, { ...before, status: "analyzing" });
    const result = await analyzeMediaSource(sourcePath, analysisDeps);
    const current = useStudio.getState();
    if (current.mediaAnalysis[assetId]?.sourcePath !== sourcePath) return;
    if (result.thumbnailPath) {
      current.setThumbnail(assetId, result.thumbnailPath);
      const t = Math.min(1, (result.probe?.durationSec ?? 1) / 2);
      current.recordThumbnailCache(sourcePath, t, 1);
    }
    if (result.proxyPath) {
      current.setPreviewProxy(assetId, result.proxyPath);
      const p = result.probe;
      current.recordProxyCache(sourcePath, `${p?.videoCodec ?? "na"}+${p?.audioCodec ?? "na"}`, 1);
    }
    current.setMediaAnalysis(assetId, { sourcePath, ...result });
  });
}

export function MediaPanel() {
  const { project, importProbedMedia, relinkMedia, thumbnails, mediaAnalysis } = useStudio();
  const [busy, setBusy] = useState(false);
  const assetSignature = useMemo(
    () => project.assets.map((a) => `${a.id}:${a.sourcePath}`).join("|"),
    [project.assets],
  );

  useEffect(() => {
    for (const asset of useStudio.getState().project.assets) {
      scheduleAnalysis(asset.id, asset.sourcePath);
    }
  }, [assetSignature]);

  async function importFile() {
    setBusy(true);
    try {
      const path = await selectMediaFile();
      if (!path) return;
      const probe = await probeMedia(path);
      if (probe.probeStatus !== "ok") {
        useStudio.setState({ lastError: `probe failed: ${probe.error ?? probe.probeStatus}` });
        return;
      }
      const clipId = importProbedMedia(probe);
      if (!clipId) return;
      scheduleAnalysis(probe.id, probe.sourcePath, probe);
    } finally {
      setBusy(false);
    }
  }

  async function relink(assetId: string) {
    const path = await selectMediaFile();
    if (!path) return;
    const probe = await probeMedia(path);
    if (probe.probeStatus !== "ok") {
      useStudio.setState({ lastError: `relink probe failed: ${probe.error ?? probe.probeStatus}` });
      return;
    }
    if (relinkMedia(assetId, probe)) {
      scheduleAnalysis(assetId, probe.sourcePath, probe);
    }
  }

  return (
    <div className="panel media-panel">
      <div className="panel-head">
        <span>Media</span>
        <button onClick={importFile} disabled={busy}>{busy ? "…" : "Import"}</button>
      </div>
      <div className="media-bin" data-testid="media-bin">
        {project.assets.length === 0 && <div className="empty-hint">No media imported yet.</div>}
        {project.assets.map((a) => {
          const analysis = mediaAnalysis[a.id];
          const probe = analysis?.probe;
          const missing = analysis?.status === "missing";
          return (
            <div key={a.id} className={`media-item${missing ? " missing" : ""}`} data-testid={`media-item-${a.id}`}>
              <div className="media-thumb">
                {thumbnails[a.id]
                  ? <img src={previewUrlForPath(thumbnails[a.id])} alt="" data-testid={`thumbnail-${a.id}`} />
                  : <span className="kind-badge">{a.kind}</span>}
              </div>
              <div className="media-meta">
                <div className="media-name">{a.name}</div>
                <div className="media-sub" data-testid={`metadata-${a.id}`}>
                  {probe?.width || a.width || "?"}×{probe?.height || a.height || "?"} · {(probe?.durationSec ?? a.durationSec).toFixed(1)}s
                  {(probe?.fps ?? a.fps) ? ` · ${(probe?.fps ?? a.fps)!.toFixed(2)} fps` : ""}
                </div>
                <div className="media-sub media-codecs">
                  V {probe?.videoCodec ?? "—"} · A {probe?.audioCodec ?? "—"} · Audio {(probe?.hasAudio ?? a.hasAudio) ? "yes" : "no"}
                </div>
                <div className={`analysis-status ${analysis?.status ?? "queued"}`} data-testid={`analysis-status-${a.id}`}>
                  {analysis?.status ?? "queued"}
                </div>
                {analysis?.waveformPath && (
                  <img className="media-waveform" src={previewUrlForPath(analysis.waveformPath)} alt="Audio waveform" data-testid={`waveform-${a.id}`} />
                )}
                {missing && (
                  <button className="relink-button" onClick={() => void relink(a.id)} data-testid={`relink-${a.id}`}>Relink</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="rail-section">Text</div>
      <CaptionPanel />
      <div className="rail-section">Audio</div>
      <div className="rail-section">Effects</div>
      <div className="rail-section">Transitions</div>
      <div className="rail-section ai">AI</div>
    </div>
  );
}
