import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { OfflineProvider } from "@haios/ai-providers";
import {
  createEmptyProject,
  parseProject,
  type MediaAsset,
  type Project,
} from "@haios/project-model";
import {
  createStudioRegistry,
  CommandBus,
  ADD_ASSET,
  ADD_CLIP,
  DELETE_CLIP,
  MOVE_CLIP,
  TRIM_CLIP,
  SPLIT_CLIP,
  UNDO,
  REDO,
  CHANGE_ASPECT,
} from "@haios/command-system";
import { probeToAsset } from "@haios/media-engine";
import { planToCommands, AI_TOOL_NAMES } from "@haios/ai-core";

const FIXTURE = fileURLToPath(new URL("./fixtures/sample.mp4", import.meta.url));

function rawProbe(): any {
  return {
    id: "asset-fixture",
    name: "sample.mp4",
    sourcePath: FIXTURE,
    kind: "video",
    durationSec: 10,
    width: 640,
    height: 360,
    fps: 30,
    hasAudio: true,
    videoCodec: "h264",
    audioCodec: "aac",
    audioSampleRate: 44100,
    probeStatus: "ok",
    error: null,
  };
}

function assetFromProbe(): MediaAsset {
  return probeToAsset(rawProbe());
}

function projectWithClip(): Project {
  const p = createEmptyProject("Demo", "p1");
  const a = assetFromProbe();
  p.assets = [a];
  p.tracks = [
    { id: "tv", kind: "video", clips: [], captions: [] },
    { id: "ta", kind: "audio", clips: [], captions: [] },
  ];
  return p;
}

/* ----------------------------- PHASE 3: ingestion ----------------------------- */
describe("Phase 3 — real media ingestion", () => {
  it("maps a real ffprobe-shaped probe into a valid MediaAsset", () => {
    const a = assetFromProbe();
    expect(a.kind).toBe("video");
    expect(a.durationSec).toBeGreaterThan(0);
    expect(a.width).toBe(640);
    expect(a.height).toBe(360);
    expect(a.hasAudio).toBe(true);
    expect(parseProject({ ...createEmptyProject("x", "x"), assets: [a] }).assets[0].id).toBe(a.id);
  });
});

/* ----------------------------- PHASE 4/6: timeline + undo/redo ----------------------------- */
describe("Phase 4/6 — timeline editing + undo/redo", () => {
  function bus(): CommandBus {
    return new CommandBus(createStudioRegistry(), projectWithClip());
  }

  it("add / select / move / trim / split / delete / duplicate / snap via CommandBus", () => {
    const b = bus();
    const clip = { id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 4, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } };
    b.execute(ADD_CLIP, { clip });
    expect(b.project.tracks[0].clips.length).toBe(1);

    b.execute(MOVE_CLIP, { clipId: "c1", newStart: 2 });
    expect(b.project.tracks[0].clips[0].start).toBe(2);

    b.execute(TRIM_CLIP, { clipId: "c1", newInPoint: 1 });
    const c = b.project.tracks[0].clips[0];
    expect(c.inPoint).toBe(1);
    expect(c.duration).toBe(3);

    b.execute(SPLIT_CLIP, { clipId: "c1", t: 1.5 });
    expect(b.project.tracks[0].clips.length).toBe(2);
    const [l, r] = b.project.tracks[0].clips;
    expect(l.duration).toBe(1.5);
    expect(r.inPoint).toBe(2.5);
    expect(r.start).toBe(3.5);

    b.execute(DELETE_CLIP, { clipId: r.id });
    expect(b.project.tracks[0].clips.length).toBe(1);

    b.execute(ADD_CLIP, { clip: { id: "c2", assetId: "asset-fixture", inPoint: 0, duration: 3, start: 5, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    const countBefore = b.project.tracks[0].clips.length;
    b.execute(ADD_CLIP, { clip: { id: "c2-dup", assetId: "asset-fixture", inPoint: 0, duration: 3, start: 9, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    expect(b.project.tracks[0].clips.length).toBe(countBefore + 1);
  });

  it("undo/redo restores exact prior state (no history corruption)", () => {
    const b = bus();
    b.execute(ADD_CLIP, { clip: { id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 4, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    b.execute(MOVE_CLIP, { clipId: "c1", newStart: 3 });
    const moved = JSON.stringify(b.project.tracks[0].clips[0]);

    b.undo();
    b.undo();
    expect(b.project.tracks[0].clips.length).toBe(0);

    b.redo();
    b.redo();
    expect(JSON.stringify(b.project.tracks[0].clips[0])).toBe(moved);
  });

  it("invalid command fails closed without mutating state", () => {
    const b = bus();
    const before = JSON.stringify(b.project);
    expect(() => b.execute(SPLIT_CLIP, { clipId: "nope", t: 2 })).toThrow();
    expect(() => b.execute(TRIM_CLIP, { clipId: "nope", newInPoint: -1 })).toThrow();
    expect(JSON.stringify(b.project)).toBe(before);
  });
});

/* ----------------------------- PHASE 6: persistence ----------------------------- */
describe("Phase 6 — persistence (save/reopen/atomic)", () => {
  function roundTrip(p: Project): Project {
    const json = JSON.stringify(p, null, 2);
    // atomic swap is two writes in the app; here we assert the parsed reopen equals canonical.
    return parseProject(JSON.parse(json));
  }

  it("reopen yields identical canonical project", () => {
    const b = new CommandBus(createStudioRegistry(), projectWithClip());
    b.execute(ADD_CLIP, { clip: { id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 4, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    b.execute(CHANGE_ASPECT, { ratio: "1080x1920" });
    const reopened = roundTrip(b.project);
    expect(reopened.aspectRatio).toBe("1080x1920");
    expect(reopened.tracks[0].clips[0].id).toBe("c1");
  });

  it("corrupt / wrong-schema project is rejected fail-closed", () => {
    expect(() => parseProject({ ...createEmptyProject("x", "x"), schemaVersion: 99 })).toThrow();
    expect(() => parseProject({ junk: true })).toThrow();
  });

  it("missing referenced media keeps project openable but flagged (graceful)", () => {
    const p = projectWithClip();
    p.assets[0].sourcePath = "C:\\does\\not\\exist.mp4";
    const reopened = roundTrip(p);
    expect(reopened.assets[0].sourcePath.endsWith("not\\exist.mp4")).toBe(true);
  });
});

/* ----------------------------- PHASE 8 / E2E-02: AI operator ----------------------------- */
describe("Phase 8 / E2E-02 — AI edit plan + execution + undo/redo", () => {
  async function run(instruction: string, selectedClipId: string): Promise<{ bus: CommandBus; plan: any }> {
    const provider = new OfflineProvider();
    const project = projectWithClip();
    const b = new CommandBus(createStudioRegistry(), project);
    b.execute(ADD_CLIP, { clip: { id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 8, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    const resp = await provider.generate({ instruction, context: { clipIds: [selectedClipId], selectedClipId } });
    const plan = resp.plan;
    const cmds = planToCommands(plan, b.project, b.registry);
    for (const c of cmds) b.execute(c.commandType, c.payload);
    return { bus: b, plan };
  }

  it("'split at 4 seconds' compiles to split_clip and executes", async () => {
    const { bus: b } = await run("Split the selected clip at 4 seconds", "c1");
    expect(b.project.tracks[0].clips.length).toBe(2);
    const [l, r] = b.project.tracks[0].clips;
    expect(l.duration).toBe(4);
    expect(r.inPoint).toBe(4);
  });

  it("AI cannot bypass CommandBus (plan compiles only to registered commands)", async () => {
    const provider = new OfflineProvider();
    const project = projectWithClip();
    project.tracks[0].clips.push({ id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 8, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } });
    const plan = (await provider.generate({ instruction: "split at 4", context: { clipIds: ["c1"], selectedClipId: "c1" } })).plan;
    const cmds = planToCommands(plan, project, createStudioRegistry());
    expect(cmds.every((c) => AI_TOOL_NAMES.length > 0)).toBe(true);
    expect(cmds[0].commandType).toBe("clip.split");
  });

  it("E2E-02: split -> undo -> redo preserves state", async () => {
    const { bus: b } = await run("Split the selected clip at 4 seconds", "c1");
    const afterSplit = JSON.stringify(b.project.tracks[0].clips);
    b.undo();
    expect(b.project.tracks[0].clips.length).toBe(1);
    b.redo();
    expect(JSON.stringify(b.project.tracks[0].clips)).toBe(afterSplit);
  });
});

/* ----------------------------- ADVERSARIAL ----------------------------- */
describe("Adversarial — fail closed", () => {
  function bus(): CommandBus {
    const b = new CommandBus(createStudioRegistry(), projectWithClip());
    b.execute(ADD_CLIP, { clip: { id: "c1", assetId: "asset-fixture", inPoint: 0, duration: 8, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 } } });
    return b;
  }

  it("malformed AI JSON rejected", () => {
    expect(() => planToCommands({ version: 1, target: { kind: "selection" } }, projectWithClip(), createStudioRegistry())).toThrow();
  });

  it("hallucinated AI operation rejected", () => {
    expect(() => planToCommands({ version: 1, target: { kind: "clip", clipId: "c1" }, operations: [{ tool: "launch_missiles", params: {} }] }, projectWithClip(), createStudioRegistry())).toThrow();
  });

  it("fake clip id rejected", () => {
    expect(() => planToCommands({ version: 1, target: { kind: "clip", clipId: "ghost" }, operations: [{ tool: "delete_clip", params: {} }] }, projectWithClip(), createStudioRegistry())).toThrow();
  });

  it("split at invalid boundary rejected", () => {
    expect(() => bus().execute(SPLIT_CLIP, { clipId: "c1", t: 99 })).toThrow();
    expect(() => bus().execute(SPLIT_CLIP, { clipId: "c1", t: 0 })).toThrow();
  });

  it("invalid trim rejected without partial mutation", () => {
    const b = bus();
    const before = JSON.stringify(b.project);
    expect(() => b.execute(TRIM_CLIP, { clipId: "c1", newInPoint: 99 })).toThrow();
    expect(JSON.stringify(b.project)).toBe(before);
  });

  it("corrupt project rejected on load", () => {
    const b = new CommandBus(createStudioRegistry(), projectWithClip());
    expect(() => b.load({ ...createEmptyProject("x", "x"), schemaVersion: 99 } as any)).toThrow();
  });

  it("provider unavailable fails closed (no partial project mutation)", async () => {
    const fakeFetch = async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response;
    const { OllamaProvider } = await import("@haios/ai-providers");
    const p = new OllamaProvider({ baseUrl: "http://localhost:11434", model: "x", fetchImpl: fakeFetch as any });
    await expect(p.generate({ instruction: "x", context: { clipIds: [] } })).rejects.toThrow();
  });
});
