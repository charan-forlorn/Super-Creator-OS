import { useState } from "react";
import { useStudio } from "../store";
import { selectMediaFile, probeMedia, ensureThumbnail, ensurePreviewProxy } from "../bridge";
import { previewNeedsProxy } from "@haios/media-engine";
import { previewUrlForPath } from "../mediaUrl";

export function MediaPanel() {
  const { project, importProbedMedia, setThumbnail, setPreviewProxy, thumbnails } = useStudio();
  const [busy, setBusy] = useState(false);

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

      // ROOT_CAUSE_1 FIX: one atomic store operation places the asset, the
      // matching track, and the clip from CURRENT state, and selects the clip.
      // This replaces the previous stale-snapshot race that silently skipped
      // clip placement on a fresh project.
      const clipId = importProbedMedia(probe);
      if (!clipId) return;

      // Non-blocking thumbnail via the deterministic cache (HIT returns the
      // existing file without re-decoding).
      try {
        const t = Math.min(1, probe.durationSec / 2);
        const thumbOut = await ensureThumbnail(path, t);
        useStudio.getState().recordThumbnailCache(path, t, 1);
        setThumbnail(probe.id, thumbOut);
      } catch {
        /* thumbnail optional */
      }

      // ROOT_CAUSE_3: deterministically decide whether the original can be
      // previewed directly, or a cached H.264/AAC proxy is required. The proxy
      // is written into the managed cache directory with a deterministic key so
      // re-importing the same source HITs the existing proxy (no re-encode).
      if (previewNeedsProxy({ kind: probe.kind as any, videoCodec: probe.videoCodec, audioCodec: probe.audioCodec })) {
        try {
          const sig = `${probe.videoCodec ?? "na"}+${probe.audioCodec ?? "na"}`;
          const proxyOut = await ensurePreviewProxy(path, probe.videoCodec, probe.audioCodec);
          useStudio.getState().recordProxyCache(path, sig, 1);
          setPreviewProxy(probe.id, proxyOut);
        } catch {
          /* proxy optional; original is still used, error surfaced via diagnostics */
        }
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel media-panel">
      <div className="panel-head">
        <span>Media</span>
        <button onClick={importFile} disabled={busy}>{busy ? "…" : "Import"}</button>
      </div>
      <div className="media-bin">
        {project.assets.length === 0 && <div className="empty-hint">No media imported yet.</div>}
        {project.assets.map((a) => (
          <div key={a.id} className="media-item">
            <div className="media-thumb">
              {thumbnails[a.id] ? <img src={previewUrlForPath(thumbnails[a.id])} alt="" /> : <span className="kind-badge">{a.kind}</span>}
            </div>
            <div className="media-meta">
              <div className="media-name">{a.name}</div>
              <div className="media-sub">
                {a.width || "?"}×{a.height || "?"} · {a.durationSec.toFixed(1)}s
                {a.hasAudio ? " · ♪" : ""}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="rail-section">Text</div>
      <div className="rail-section">Captions</div>
      <div className="rail-section">Audio</div>
      <div className="rail-section">Effects</div>
      <div className="rail-section">Transitions</div>
      <div className="rail-section ai">AI</div>
    </div>
  );
}
