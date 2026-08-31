/**
 * Deterministic media cache lifecycle (R2.2).
 *
 * A small, side-effect-free cache manager that tracks proxy + thumbnail entries
 * and their lifecycle state so the UI can decide HIT / MISS / STALE / INVALIDATE
 * / REBUILD without touching the filesystem. The actual file ownership lives in
 * the Rust backend (`generate_preview_proxy` / `generate_thumbnail`); this layer
 * records the deterministic identity + mtime that the GUI and store consume.
 *
 * This module deliberately performs NO I/O so it is unit-testable in a browser
 * context and never leaks node-only APIs into the frontend bundle.
 */

import {
  cachePath,
  cacheFileName,
  proxyCacheKey,
  thumbnailCacheKey,
  type CacheKind,
} from "./cacheKey.js";

export type CacheState = "missing" | "fresh" | "stale";

export interface CacheEntry {
  kind: CacheKind;
  key: string;
  /** Deterministic cache path (computed, not probed). */
  path: string;
  /** Monotonic source revision this entry was built against. */
  builtForRevision: number;
  /** Wall-clock ms when the entry was recorded as built. */
  builtAt: number;
  /** The source media path this entry derives from (cache ownership). */
  sourcePath: string;
}

export interface CacheRecord {
  entry: CacheEntry;
  /** Current lifecycle state relative to `currentRevision`. */
  state: CacheState;
}

/** Identity + state for a proxy request (no IO). */
export function describeProxy(
  cacheDir: string,
  sourcePath: string,
  codecSignature: string,
  builtRevision: number | null,
  currentRevision: number,
  builtAt: number,
): CacheRecord {
  const key = proxyCacheKey(sourcePath, codecSignature);
  const entry: CacheEntry = {
    kind: "proxy",
    key,
    path: cachePath(cacheDir, "proxy", key),
    builtForRevision: builtRevision ?? -1,
    builtAt,
    sourcePath,
  };
  const state: CacheState = builtRevision === null ? "missing" : builtRevision < currentRevision ? "stale" : "fresh";
  return { entry, state };
}

/** Identity + state for a thumbnail request (no IO). */
export function describeThumbnail(
  cacheDir: string,
  sourcePath: string,
  timeSec: number,
  builtRevision: number | null,
  currentRevision: number,
  builtAt: number,
): CacheRecord {
  const key = thumbnailCacheKey(sourcePath, timeSec);
  const entry: CacheEntry = {
    kind: "thumbnail",
    key,
    path: cachePath(cacheDir, "thumbnail", key),
    builtForRevision: builtRevision ?? -1,
    builtAt,
    sourcePath,
  };
  const state: CacheState = builtRevision === null ? "missing" : builtRevision < currentRevision ? "stale" : "fresh";
  return { entry, state };
}

/**
 * In-memory registry of built cache entries keyed by deterministic cache key.
 * Tracks the source revision each entry was built against so STALE can be
 * detected when the source media (or its derived identity) changes.
 */
export class PureMediaCache {
  private entries = new Map<string, CacheEntry>();

  constructor(private cacheDir: string) {}

  /** Record a successfully built proxy entry for `sourcePath` at `revision`. */
  recordProxy(sourcePath: string, codecSignature: string, revision: number, builtAt = Date.now()): CacheEntry {
    const key = proxyCacheKey(sourcePath, codecSignature);
    const entry: CacheEntry = {
      kind: "proxy",
      key,
      path: cachePath(this.cacheDir, "proxy", key),
      builtForRevision: revision,
      builtAt,
      sourcePath,
    };
    this.entries.set(key, entry);
    return entry;
  }

  /** Record a successfully built thumbnail entry for `sourcePath` @ `timeSec` at `revision`. */
  recordThumbnail(sourcePath: string, timeSec: number, revision: number, builtAt = Date.now()): CacheEntry {
    const key = thumbnailCacheKey(sourcePath, timeSec);
    const entry: CacheEntry = {
      kind: "thumbnail",
      key,
      path: cachePath(this.cacheDir, "thumbnail", key),
      builtForRevision: revision,
      builtAt,
      sourcePath,
    };
    this.entries.set(key, entry);
    return entry;
  }

  /** Inspect proxy state against the current source revision. */
  proxyState(sourcePath: string, codecSignature: string, currentRevision: number): CacheRecord {
    const key = proxyCacheKey(sourcePath, codecSignature);
    const entry = this.entries.get(key);
    if (!entry) {
      return {
        entry: { kind: "proxy", key, path: cachePath(this.cacheDir, "proxy", key), builtForRevision: -1, builtAt: 0, sourcePath },
        state: "missing",
      };
    }
    return { entry, state: entry.builtForRevision < currentRevision ? "stale" : "fresh" };
  }

  /** Inspect thumbnail state against the current source revision. */
  thumbnailState(sourcePath: string, timeSec: number, currentRevision: number): CacheRecord {
    const key = thumbnailCacheKey(sourcePath, timeSec);
    const entry = this.entries.get(key);
    if (!entry) {
      return {
        entry: { kind: "thumbnail", key, path: cachePath(this.cacheDir, "thumbnail", key), builtForRevision: -1, builtAt: 0, sourcePath },
        state: "missing",
      };
    }
    return { entry, state: entry.builtForRevision < currentRevision ? "stale" : "fresh" };
  }

  /** Invalidate a single entry by deterministic key (stale -> will rebuild). */
  invalidate(key: string): boolean {
    return this.entries.delete(key);
  }

  /** Remove every entry (full cache reset). */
  clear(): void {
    this.entries.clear();
  }

  /** Invalidate every entry for a given source path (proxy + all thumbnails). */
  invalidateSource(sourcePath: string): number {
    let n = 0;
    for (const [key, entry] of [...this.entries.entries()]) {
      if (entry.sourcePath === sourcePath) {
        if (this.entries.delete(key)) n++;
      }
    }
    return n;
  }

  /** Number of live entries. */
  get size(): number {
    return this.entries.size;
  }

  /** All live entries (for cache-owned UI lists / diagnostics). */
  list(): CacheEntry[] {
    return [...this.entries.values()];
  }

  /** Deterministic file name helper re-exported for the GUI. */
  static fileName(kind: CacheKind, key: string): string {
    return cacheFileName(kind, key);
  }
}
