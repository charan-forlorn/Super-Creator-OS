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
import { type CacheKind } from "./cacheKey.js";
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
export declare function describeProxy(cacheDir: string, sourcePath: string, codecSignature: string, builtRevision: number | null, currentRevision: number, builtAt: number): CacheRecord;
/** Identity + state for a thumbnail request (no IO). */
export declare function describeThumbnail(cacheDir: string, sourcePath: string, timeSec: number, builtRevision: number | null, currentRevision: number, builtAt: number): CacheRecord;
/**
 * In-memory registry of built cache entries keyed by deterministic cache key.
 * Tracks the source revision each entry was built against so STALE can be
 * detected when the source media (or its derived identity) changes.
 */
export declare class PureMediaCache {
    private cacheDir;
    private entries;
    constructor(cacheDir: string);
    /** Record a successfully built proxy entry for `sourcePath` at `revision`. */
    recordProxy(sourcePath: string, codecSignature: string, revision: number, builtAt?: number): CacheEntry;
    /** Record a successfully built thumbnail entry for `sourcePath` @ `timeSec` at `revision`. */
    recordThumbnail(sourcePath: string, timeSec: number, revision: number, builtAt?: number): CacheEntry;
    /** Inspect proxy state against the current source revision. */
    proxyState(sourcePath: string, codecSignature: string, currentRevision: number): CacheRecord;
    /** Inspect thumbnail state against the current source revision. */
    thumbnailState(sourcePath: string, timeSec: number, currentRevision: number): CacheRecord;
    /** Invalidate a single entry by deterministic key (stale -> will rebuild). */
    invalidate(key: string): boolean;
    /** Remove every entry (full cache reset). */
    clear(): void;
    /** Invalidate every entry for a given source path (proxy + all thumbnails). */
    invalidateSource(sourcePath: string): number;
    /** Number of live entries. */
    get size(): number;
    /** All live entries (for cache-owned UI lists / diagnostics). */
    list(): CacheEntry[];
    /** Deterministic file name helper re-exported for the GUI. */
    static fileName(kind: CacheKind, key: string): string;
}
