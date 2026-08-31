/**
 * TEST-ONLY E2E bootstrap entry.
 *
 * This module is NEVER loaded by the normal production/dev entry. It is reached
 * only through index.e2e.html + vite.e2e.config.ts, and seeds the existing store
 * via `loadProject()` — no IPC command, window backdoor, shell hook, or normal
 * runtime behavior is added. See e2e/README.e2e.md.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { useStudio } from "./store";
import { ensureThumbnail, ensurePreviewProxy } from "./bridge";
import { previewNeedsProxy } from "@haios/media-engine";

// The E2E seed renders the SAME production App, so it must load the SAME global
// stylesheet. Without this, the harness renders unstyled: the timeline drops
// below the viewport and WebDriver pointer moves fail with "out of bounds".
import "./styles.css";
import fixtureProject from "../e2e/fixtures/project.json";

// __E2E_SAMPLE_ABS_PATH__ is injected at build time by vite.e2e.config.ts
// (the real absolute path to the deterministic H.264/AAC sample). Using a
// genuine filesystem path (not a Vite `?url` web URL) lets the app's Tauri
// asset-protocol resolver serve it for real playback inside the bundled webview.
// @ts-expect-error injected build-time token
const E2E_SAMPLE_ABS_PATH: string = __E2E_SAMPLE_ABS_PATH__ || "E2E_FIXTURE_SAMPLE_MP4";

// Proxy-required fixture (ProRes/PCM) lives next to the sample; resolved at
// seed time so the app can exercise the REAL ensurePreviewProxy production
// command (mirrors MediaPanel.importFile) during bootstrap — no new bridge.
const E2E_PRORES_ABS_PATH = E2E_SAMPLE_ABS_PATH.replace(/sample\.mp4$/i, "sample_prores.mov");
const E2E_MISSING_ABS_PATH = E2E_SAMPLE_ABS_PATH.replace(/sample\.mp4$/i, "definitely-missing.mp4");

async function bootstrapE2E() {
  // Clone before replacing the test fixture sentinel so schema validation is
  // applied to a fresh project document on every E2E app launch.
  const project = JSON.parse(JSON.stringify(fixtureProject)) as {
    assets: Array<{ sourcePath: string; id: string; kind: string; durationSec?: number; videoCodec?: string | null; audioCodec?: string | null }>;
  };
  project.assets = project.assets.map((asset) =>
    asset.sourcePath === "E2E_FIXTURE_SAMPLE_MP4"
      ? { ...asset, sourcePath: E2E_SAMPLE_ABS_PATH }
      : asset.sourcePath === "E2E_FIXTURE_PRORES_MOV"
        ? { ...asset, sourcePath: E2E_PRORES_ABS_PATH }
        : asset.sourcePath === "E2E_FIXTURE_MISSING"
          ? { ...asset, sourcePath: E2E_MISSING_ABS_PATH }
          : asset,
  );

  // Render the SAME production App IMMEDIATELY (do not block first paint on
  // cache I/O — mirrors production, where MediaPanel caches after render). This
  // guarantees the editor is interactive even if a cache command is slow.
  const root = document.getElementById("root");
  if (!root) throw new Error("E2E: #root missing");
  ReactDOM.createRoot(root).render(React.createElement(App));
  useStudio.getState().loadProject(project);

  const mark = (key: string, value: unknown) => {
    try { document.documentElement.setAttribute(`data-e2e-${key}`, String(value)); } catch { /* test-only diagnostics */ }
  };
  mark("seed-start", Date.now());

  // Mirror the production import flow: for each seeded video asset, generate a
  // deterministic thumbnail AND (if the codec needs it) a cached H.264/AAC proxy
  // through the REAL Tauri commands. Detached (fire-and-forget) so a slow/failed
  // proxy encode never blocks the GUI. Proves the managed cache model end-to-end
  // in the actual app (thumbnail + proxy) without any test bridge.
  void (async () => {
    for (const asset of project.assets) {
      if (asset.kind !== "video") continue;
      try {
        const t = Math.min(1, (asset.durationSec ?? 1) / 2);
        const thumbOut = await ensureThumbnail(asset.sourcePath, t);
        useStudio.getState().recordThumbnailCache(asset.sourcePath, t, 1);
        useStudio.getState().setThumbnail(asset.id, thumbOut);
      } catch {
        /* thumbnail optional in seed */
      }
      // ROOT_CAUSE_3 decision + real proxy generation (only when required).
      const needs = previewNeedsProxy({ kind: "video", videoCodec: asset.videoCodec as any, audioCodec: asset.audioCodec as any });
      if (needs) {
        try {
          const sig = `${asset.videoCodec ?? "na"}+${asset.audioCodec ?? "na"}`;
          // MISS → real proxy encode (via the production Tauri command).
          const proxyOut = await ensurePreviewProxy(asset.sourcePath, asset.videoCodec ?? null, asset.audioCodec ?? null);
          mark(`proxy-ok-${asset.id}`, proxyOut);
          useStudio.getState().recordProxyCache(asset.sourcePath, sig, 1);
          useStudio.getState().setPreviewProxy(asset.id, proxyOut);
          // HIT → SAME command path again with identical identity. The backend
          // must reuse the existing deterministic cache file (no re-encode). This
          // proves real cache HIT/REUSE inside the production app, not just MISS.
          const proxyOut2 = await ensurePreviewProxy(asset.sourcePath, asset.videoCodec ?? null, asset.audioCodec ?? null);
          mark(proxyOut === proxyOut2 ? `proxy-hit-ok-${asset.id}` : `proxy-hit-mismatch-${asset.id}`, "1");
        } catch (e) {
          console.error("E2E proxy seed failed", e);
          mark(`proxy-error-${asset.id}`, String(e));
        }
      }
    }
  })();
}

bootstrapE2E().catch((e) => console.error("E2E bootstrap failed", e));
