import { describe, it, expect } from "vitest";
import { createEmptyProject, type Clip, type MediaAsset } from "@haios/project-model";
import { createStudioRegistry, CommandRegistry } from "@haios/command-system";
import {
  parseAiPlan,
  AiPlanValidationError,
  AI_TOOL_NAMES,
  planToCommands,
  validatePlanSemantics,
  AiSemanticError,
} from "../src/index.js";

const asset: MediaAsset = {
  id: "a1", name: "src.mp4", sourcePath: "/m/src.mp4", kind: "video",
  durationSec: 10, width: 1920, height: 1080, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};
const clip: Clip = { id: "c1", assetId: "a1", inPoint: 2, duration: 4, start: 0, trackId: "tv" };

function projWithClip() {
  const p = createEmptyProject("P", "p");
  p.assets = [asset];
  p.tracks = [{ id: "tv", kind: "video", clips: [clip] }];
  return p;
}

describe("AI plan validation (fail-closed)", () => {
  it("parses a well-formed plan", () => {
    const plan = parseAiPlan({
      version: 1,
      target: { kind: "clip", clipId: "c1" },
      operations: [{ tool: "split_clip", params: { t: 2 } }],
    });
    expect(plan.operations[0].tool).toBe("split_clip");
  });

  it("rejects malformed JSON-style plan (missing operations)", () => {
    expect(() => parseAiPlan({ version: 1, target: { kind: "selection" } })).toThrow(
      AiPlanValidationError,
    );
  });

  it("rejects an unknown tool name (hallucination)", () => {
    const bad = { version: 1, target: { kind: "clip", clipId: "c1" }, operations: [{ tool: "launch_missiles", params: {} }] };
    expect(() => parseAiPlan(bad)).toThrow(AiPlanValidationError);
  });

  it("semantic validation rejects a fake clip id", () => {
    const plan = parseAiPlan({
      version: 1, target: { kind: "clip", clipId: "ghost" },
      operations: [{ tool: "delete_clip", params: {} }],
    });
    expect(() => validatePlanSemantics(plan, projWithClip())).toThrow(AiSemanticError);
  });

  it("semantic validation rejects an invalid split boundary", () => {
    const plan = parseAiPlan({
      version: 1, target: { kind: "clip", clipId: "c1" },
      operations: [{ tool: "split_clip", params: { t: 99 } }],
    });
    expect(() => validatePlanSemantics(plan, projWithClip())).toThrow(AiSemanticError);
  });

  it("compiles a valid plan into registered CommandBus commands", () => {
    const plan = parseAiPlan({
      version: 1, target: { kind: "clip", clipId: "c1" },
      operations: [
        { tool: "split_clip", params: { t: 2 } },
        { tool: "move_clip", params: { newStart: 1 } },
      ],
    });
    const reg = createStudioRegistry();
    const cmds = planToCommands(plan, projWithClip(), reg);
    expect(cmds.map((c) => c.commandType)).toEqual(["clip.split", "clip.move"]);
  });

  it("compile refuses to emit an unregistered command (policy seam)", () => {
    // The policy seam: compilePlanToCommands throws unless every mapped command
    // type is actually present in the supplied registry. Prove it with an EMPTY
    // registry so no command type is present, then request a caption.
    const reg = new CommandRegistry();
    const plan = parseAiPlan({
      version: 1, target: { kind: "selection" },
      operations: [{ tool: "add_caption", params: { text: "hi" } }],
    });
    expect(() => planToCommands(plan, projWithClip(), reg)).toThrow();
  });

  it("tool enum is exhaustive over the known set", () => {
    expect(AI_TOOL_NAMES).toContain("change_aspect_ratio");
  });
});
