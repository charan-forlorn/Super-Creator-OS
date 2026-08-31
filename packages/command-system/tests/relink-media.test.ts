import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { CommandBus } from "../src/bus.js";
import { createStudioRegistry, PLACE_PROBED_MEDIA, RELINK_MEDIA } from "../src/index.js";

function seededBus() {
  const bus = new CommandBus(createStudioRegistry(), createEmptyProject("Relink", "p1"));
  bus.execute(PLACE_PROBED_MEDIA, {
    probe: { id: "a1", name: "old.mp4", sourcePath: "C:/old.mp4", kind: "video", durationSec: 10,
      width: 640, height: 360, fps: 30, hasAudio: true, videoCodec: "h264", audioCodec: "aac", probeStatus: "ok" },
    place: true,
  });
  return bus;
}

describe("media.relink", () => {
  it("updates source metadata while preserving asset identity and supports undo", () => {
    const bus = seededBus();
    bus.execute(RELINK_MEDIA, {
      assetId: "a1",
      probe: { name: "new.mp4", sourcePath: "D:/new.mp4", kind: "video", durationSec: 12,
        width: 1920, height: 1080, fps: 60, hasAudio: true, videoCodec: "h264", audioCodec: "aac", probeStatus: "ok" },
    });
    const a = bus.project.assets.find((x) => x.id === "a1")!;
    expect(a.id).toBe("a1");
    expect(a.sourcePath).toBe("D:/new.mp4");
    expect(a.width).toBe(1920);
    expect(a.fps).toBe(60);
    expect(bus.undo()).toBe(true);
    expect(bus.project.assets.find((x) => x.id === "a1")!.sourcePath).toBe("C:/old.mp4");
  });
  it("fails closed when replacement media is too short for existing clips", () => {
    const bus = seededBus();
    expect(() => bus.execute(RELINK_MEDIA, {
      assetId: "a1",
      probe: { name: "short.mp4", sourcePath: "D:/short.mp4", kind: "video", durationSec: 2,
        width: 640, height: 360, fps: 30, hasAudio: true, videoCodec: "h264", audioCodec: "aac", probeStatus: "ok" },
    })).toThrow(/RELINK_INCOMPATIBLE_CLIP/);
    expect(bus.project.assets.find((x) => x.id === "a1")!.sourcePath).toBe("C:/old.mp4");
  });
});
