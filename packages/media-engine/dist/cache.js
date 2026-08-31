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
import { cachePath, cacheFileName, proxyCacheKey, thumbnailCacheKey, } from "./cacheKey.js";
/** Identity + state for a proxy request (no IO). */
export function describeProxy(cacheDir, sourcePath, codecSignature, builtRevision, currentRevision, builtAt) {
    const key = proxyCacheKey(sourcePath, codecSignature);
    const entry = {
        kind: "proxy",
        key,
        path: cachePath(cacheDir, "proxy", key),
        builtForRevision: builtRevision ?? -1,
        builtAt,
        sourcePath,
    };
    const state = builtRevision === null ? "missing" : builtRevision < currentRevision ? "stale" : "fresh";
    return { entry, state };
}
/** Identity + state for a thumbnail request (no IO). */
export function describeThumbnail(cacheDir, sourcePath, timeSec, builtRevision, currentRevision, builtAt) {
    const key = thumbnailCacheKey(sourcePath, timeSec);
    const entry = {
        kind: "thumbnail",
        key,
        path: cachePath(cacheDir, "thumbnail", key),
        builtForRevision: builtRevision ?? -1,
        builtAt,
        sourcePath,
    };
    const state = builtRevision === null ? "missing" : builtRevision < currentRevision ? "stale" : "fresh";
    return { entry, state };
}
/**
 * In-memory registry of built cache entries keyed by deterministic cache key.
 * Tracks the source revision each entry was built against so STALE can be
 * detected when the source media (or its derived identity) changes.
 */
export class PureMediaCache {
    cacheDir;
    entries = new Map();
    constructor(cacheDir) {
        this.cacheDir = cacheDir;
    }
    /** Record a successfully built proxy entry for `sourcePath` at `revision`. */
    recordProxy(sourcePath, codecSignature, revision, builtAt = Date.now()) {
        const key = proxyCacheKey(sourcePath, codecSignature);
        const entry = {
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
    recordThumbnail(sourcePath, timeSec, revision, builtAt = Date.now()) {
        const key = thumbnailCacheKey(sourcePath, timeSec);
        const entry = {
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
    proxyState(sourcePath, codecSignature, currentRevision) {
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
    thumbnailState(sourcePath, timeSec, currentRevision) {
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
    invalidate(key) {
        return this.entries.delete(key);
    }
    /** Remove every entry (full cache reset). */
    clear() {
        this.entries.clear();
    }
    /** Invalidate every entry for a given source path (proxy + all thumbnails). */
    invalidateSource(sourcePath) {
        let n = 0;
        for (const [key, entry] of [...this.entries.entries()]) {
            if (entry.sourcePath === sourcePath) {
                if (this.entries.delete(key))
                    n++;
            }
        }
        return n;
    }
    /** Number of live entries. */
    get size() {
        return this.entries.size;
    }
    /** All live entries (for cache-owned UI lists / diagnostics). */
    list() {
        return [...this.entries.values()];
    }
    /** Deterministic file name helper re-exported for the GUI. */
    static fileName(kind, key) {
        return cacheFileName(kind, key);
    }
}
