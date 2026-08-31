/**
 * Deterministic media-cache identity (R2.2).
 *
 * This module is the SINGLE source of truth for how a proxy or thumbnail cache
 * entry is named and located on disk. It is intentionally browser-safe (no
 * node:fs / node:crypto imports) so the React frontend can compute cache paths
 * without pulling in server-only modules, and so the same algorithm can be
 * mirrored verbatim in the Rust backend (see src-tauri/src/bridge.rs) and
 * contract-tested across both languages.
 *
 * Cache ownership model:
 *   SOURCE MEDIA  → immutable, never cached, never mutated.
 *   PROXY         → deterministic cache identity derived from source + codec preset.
 *   THUMBNAILS    → deterministic cache identity derived from source + time bucket.
 *
 * The cache supports the required lifecycle states: hit, miss, stale, invalidate,
 * rebuild. The Rust backend owns the on-disk cache directory; this module only
 * computes the deterministic key + path so both sides agree.
 */
export type CacheKind = "proxy" | "thumbnail";
/** Normalize a codec string the same way on every platform (lowercase, alnum only). */
export declare function normalizeCodec(c: string | null | undefined): string;
/**
 * Stable 32-bit djb2 hash over the UTF-8 bytes of `input`, emitted as unsigned
 * base36. Mirrored in Rust (bridge.rs::stable_hash) so the two implementations
 * produce byte-identical keys — this is asserted by the cross-language contract
 * test. TextEncoder + Math.imul keeps the JS path identical to Rust's byte loop.
 */
export declare function stableHash(input: string): string;
/** Deterministic proxy cache key. `codecSig` folds video+audio codec into identity. */
export declare function proxyCacheKey(sourcePath: string, codecSignature: string): string;
/** Deterministic thumbnail cache key. Time is bucketed to ms for stable identity. */
export declare function thumbnailCacheKey(sourcePath: string, timeSec: number): string;
/** File name for a cache entry of the given kind + key. */
export declare function cacheFileName(kind: CacheKind, key: string): string;
/**
 * Deterministic absolute cache path: `<cacheDir>/<kind>/<key>.<ext>`.
 * Uses the platform separator so the result is a valid native path on both
 * Windows and POSIX. The directory layout nests by kind so proxy + thumbnail
 * entries never collide.
 */
export declare function cachePath(cacheDir: string, kind: CacheKind, key: string): string;
