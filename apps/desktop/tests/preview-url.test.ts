import { describe, it, expect } from "vitest";
import { resolvePreviewSource, previewUrlForPath, isRawFilesystemPath } from "../src/mediaUrl.js";
import type { MediaAsset } from "@haios/project-model";

const winAsset: MediaAsset = {
  id: "a1",
  name: "sample.mp4",
  sourcePath: "C:\\Videos\\sample.mp4",
  kind: "video",
  durationSec: 5,
  width: 1920,
  height: 1080,
  fps: 30,
  hasAudio: true,
  createdAt: "2026-08-31T00:00:00Z",
};

describe("TEST2 — preview URL must not be a raw filesystem path", () => {
  it("resolvePreviewSource does not return the raw Windows path", () => {
    const url = resolvePreviewSource(winAsset);
    expect(url).not.toBe("C:\\Videos\\sample.mp4");
    expect(isRawFilesystemPath(url)).toBe(false);
    // Must be a Tauri-safe URL (asset:// or http(s)://asset.localhost or app-local proxy)
    expect(/^(asset:\/\/|https?:\/\/asset\.localhost|https?:\/\/)/.test(url)).toBe(true);
  });

  it("previewUrlForPath converts a raw path into a safe URL", () => {
    const url = previewUrlForPath("C:\\Videos\\sample.mp4");
    expect(url).not.toContain("C:\\Videos\\sample.mp4");
    expect(isRawFilesystemPath(url)).toBe(false);
  });

  it("detects a raw path deterministically", () => {
    expect(isRawFilesystemPath("C:\\Videos\\sample.mp4")).toBe(true);
    expect(isRawFilesystemPath("/home/u/v.mp4")).toBe(true);
    expect(isRawFilesystemPath("asset://localhost/C:/Videos/sample.mp4")).toBe(false);
  });
});
