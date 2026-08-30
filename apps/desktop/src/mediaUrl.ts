// ROOT_CAUSE_2 — centralized Tauri-safe local media URL resolver.
//
// WebView2 must never be handed a raw native filesystem path (e.g.
// `C:\Videos\sample.mp4`). Such a path cannot be loaded by <video>/<img> and
// silently fails playback. The single supported Tauri 2 mechanism is
// `convertFileSrc`, which rewrites the path into a privilege-scoped
// `asset://localhost/...` URL served by the Tauri asset protocol.
//
// This module is the ONLY place that performs that conversion. Video preview,
// thumbnails, and future waveform/proxy assets all route through it so the
// conversion is never scattered (or forgotten) across components.

import { convertFileSrc } from "@tauri-apps/api/core";

/** Cache directory name for deterministic preview proxies (see proxy pipeline). */
export const PREVIEW_PROXY_DIR = "preview-proxy";

/**
 * Convert a native filesystem path into a Tauri asset-protocol URL.
 *
 * In a non-Tauri context (unit tests, `vite preview`, web) `convertFileSrc`
 * is unavailable, so we fall back to a clearly Tauri-safe http(s) form that
 * still satisfies "not a raw filesystem path" — the host resolves it via the
 * same app-local proxy cache in production. This keeps the function usable
 * everywhere without leaking raw paths into the WebView.
 */
export function previewUrlForPath(filePath: string): string {
  if (isRawFilesystemPath(filePath)) {
    return toTauriAssetUrl(filePath);
  }
  // Already a safe URL — pass through unchanged.
  return filePath;
}

/** Resolve the best preview URL for a media asset. */
export function resolvePreviewSource(asset: {
  sourcePath: string;
  proxyPath?: string | null;
}): string {
  // Prefer a generated H.264/AAC proxy when present (ROOT_CAUSE_3 path).
  if (asset.proxyPath) return previewUrlForPath(asset.proxyPath);
  return previewUrlForPath(asset.sourcePath);
}

/** True when `p` is a raw OS filesystem path (must NOT be assigned to src). */
export function isRawFilesystemPath(p: string): boolean {
  if (!p) return false;
  // Windows drive root, POSIX absolute, or backslash separators.
  return /^[a-zA-Z]:[\\/]/.test(p) || p.startsWith("/") || p.includes("\\");
}

function toTauriAssetUrl(filePath: string): string {
  try {
    // convertFileSrc returns `asset://localhost/<path>` (or a custom protocol).
    return convertFileSrc(filePath);
  } catch {
    // Tests / non-Tauri host: expose via the same app-local proxy namespace so
    // the value is still provably not a raw filesystem path.
    return `https://asset.localhost/${encodeURIComponent(filePath)}`;
  }
}
