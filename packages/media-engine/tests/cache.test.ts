import { describe, it, expect } from "vitest";
import {
  stableHash,
  proxyCacheKey,
  thumbnailCacheKey,
  cachePath,
  cacheFileName,
  PureMediaCache,
  describeProxy,
  describeThumbnail,
} from "../src/index.js";

const CACHE_DIR = "C:/Users/test/AppData/Local/haios/cache";

describe("R2.2 deterministic cache keys", () => {
  it("stableHash is deterministic and mirrors Rust djb2 base36", () => {
    expect(stableHash("hello")).toBe(stableHash("hello"));
    expect(stableHash("hello")).not.toBe(stableHash("world"));
    // djb2 over "a": h=5381, h = (h*33 + 97) wrapped to u32.
    const h = (Math.imul(5381, 33) + 97) >>> 0;
    expect(stableHash("a")).toBe(h.toString(36));
  });

  it("proxy key folds codec signature and is stable per source", () => {
    const k1 = proxyCacheKey("C:/v/sample.mp4", "h264+aac");
    const k2 = proxyCacheKey("C:/v/sample.mp4", "h264+aac");
    expect(k1).toBe(k2);
    expect(k1).toBe("proxy_" + stableHash("C:/v/sample.mp4|h264+aac"));
    const k3 = proxyCacheKey("C:/v/sample.mp4", "hevc+aac");
    expect(k3).not.toBe(k1);
  });

  it("thumbnail key buckets time and is stable", () => {
    const t = 1.234;
    const k1 = thumbnailCacheKey("C:/v/sample.mp4", t);
    const k2 = thumbnailCacheKey("C:/v/sample.mp4", t);
    expect(k1).toBe(k2);
    expect(k1).toBe("thumb_" + stableHash(`C:/v/sample.mp4|${Math.round(t * 1000)}`));
    // A different time bucket yields a different key.
    expect(thumbnailCacheKey("C:/v/sample.mp4", 5.678)).not.toBe(k1);
  });

  it("cachePath nests by kind and uses the right extension", () => {
    expect(cachePath(CACHE_DIR, "proxy", "proxy_x")).toBe(`${CACHE_DIR}/proxy/proxy_x.mp4`);
    expect(cachePath(CACHE_DIR, "thumbnail", "thumb_y")).toBe(`${CACHE_DIR}/thumbnail/thumb_y.png`);
    expect(cacheFileName("proxy", "proxy_x")).toBe("proxy_x.mp4");
  });
});

describe("R2.2 cache lifecycle (hit/miss/stale/invalidate/rebuild)", () => {
  it("records a proxy as fresh and detects staleness at higher revision", () => {
    const c = new PureMediaCache(CACHE_DIR);
    c.recordProxy("C:/v/sample.mp4", "h264+aac", 1);
    expect(c.proxyState("C:/v/sample.mp4", "h264+aac", 1).state).toBe("fresh");
    expect(c.proxyState("C:/v/sample.mp4", "h264+aac", 2).state).toBe("stale");
  });

  it("records a thumbnail as fresh and detects staleness", () => {
    const c = new PureMediaCache(CACHE_DIR);
    c.recordThumbnail("C:/v/sample.mp4", 1.0, 3);
    expect(c.thumbnailState("C:/v/sample.mp4", 1.0, 3).state).toBe("fresh");
    expect(c.thumbnailState("C:/v/sample.mp4", 1.0, 4).state).toBe("stale");
  });

  it("reports missing for an unrecorded source", () => {
    const c = new PureMediaCache(CACHE_DIR);
    expect(c.proxyState("C:/v/other.mp4", "h264+aac", 1).state).toBe("missing");
    expect(c.thumbnailState("C:/v/other.mp4", 2.0, 1).state).toBe("missing");
  });

  it("invalidate removes a single entry", () => {
    const c = new PureMediaCache(CACHE_DIR);
    const e = c.recordProxy("C:/v/sample.mp4", "h264+aac", 1);
    expect(c.invalidate(e.key)).toBe(true);
    expect(c.proxyState("C:/v/sample.mp4", "h264+aac", 1).state).toBe("missing");
  });

  it("invalidateSource drops proxy + thumbnails for the same source", () => {
    const c = new PureMediaCache(CACHE_DIR);
    c.recordProxy("C:/v/sample.mp4", "h264+aac", 1);
    c.recordThumbnail("C:/v/sample.mp4", 1.0, 1);
    c.recordThumbnail("C:/v/sample.mp4", 2.0, 1);
    const removed = c.invalidateSource("C:/v/sample.mp4");
    expect(removed).toBe(3);
    expect(c.size).toBe(0);
  });

  it("describeProxy/describeThumbnail expose path + state without IO", () => {
    const p = describeProxy(CACHE_DIR, "C:/v/sample.mp4", "h264+aac", 5, 6, Date.now());
    expect(p.state).toBe("stale");
    expect(p.entry.path.endsWith(".mp4")).toBe(true);
    const t = describeThumbnail(CACHE_DIR, "C:/v/sample.mp4", 1.0, null, 1, Date.now());
    expect(t.state).toBe("missing");
    expect(t.entry.path.endsWith(".png")).toBe(true);
  });
});
