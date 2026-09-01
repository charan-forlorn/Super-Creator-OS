import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { compileCompositionPlan, parseProject, type Clip, type MediaAsset, type Track } from "@haios/project-model";
import { PreviewCompositionStage } from "../src/components/Preview";
import { compilePreviewFrame } from "../src/previewComposition";

const asset = (id: string, kind: "video" | "audio", hasAudio = true): MediaAsset => ({
  id, name: `${id}.mp4`, sourcePath: `C:/media/${id}.mp4`, kind,
  durationSec: 10, width: 1920, height: 1080, fps: kind === "video" ? 30 : undefined,
  hasAudio, createdAt: "2026-01-01T00:00:00Z",
});
function clip(id: string, assetId: string, trackId: string): Clip {
  return {
    id, assetId, trackId, start: 0, inPoint: 0, duration: 5, playbackRate: 1,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false },
    effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn: null,
  };
}
function track(id: string, kind: Track["kind"], clips: Clip[]): Track {
  return { id, kind, clips, captions: [], visible: true, muted: false, locked: false };
}
function previewProps() {
  const assets = [asset("back", "video"), asset("front", "video"), asset("music", "audio")];
  const tracks = [
    track("v-back", "video", [clip("back-c", "back", "v-back")]),
    track("v-front", "video", [clip("front-c", "front", "v-front")]),
    track("a-music", "audio", [clip("music-c", "music", "a-music")]),
  ];
  const project = parseProject({
    schemaVersion: 2, id: "preview-render", name: "Preview Render",
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    assets, tracks, durationSec: 5, aspectRatio: "1920x1080",
  });
  return {
    frame: compilePreviewFrame(compileCompositionPlan(project), 1),
    aspectRatio: project.aspectRatio,
    previewProxies: {}, transportRate: 0 as const, projectDuration: project.durationSec,
    setPlayhead: () => undefined, setTransportRate: () => undefined,
  };
}

describe("P4.3 Preview CompositionPlan render cutover", () => {
  it("renders every active visual layer in canonical order", () => {
    const html = renderToStaticMarkup(createElement(PreviewCompositionStage, previewProps()));
    expect(html).toContain('data-preview-layer="v-back"');
    expect(html).toContain('data-preview-layer="v-front"');
    expect(html.indexOf('data-preview-layer="v-back"')).toBeLessThan(html.indexOf('data-preview-layer="v-front"'));
  });
  it("renders composition audio as dedicated audio elements while visual videos stay muted", () => {
    const html = renderToStaticMarkup(createElement(PreviewCompositionStage, previewProps()));
    expect(html).toContain('data-preview-audio="back-c"');
    expect(html).toContain('data-preview-audio="front-c"');
    expect(html).toContain('data-preview-audio="music-c"');
    expect((html.match(/data-preview-visual=/g) ?? [])).toHaveLength(2);
    expect((html.match(/muted=""/g) ?? []).length).toBeGreaterThanOrEqual(2);
  });
});
