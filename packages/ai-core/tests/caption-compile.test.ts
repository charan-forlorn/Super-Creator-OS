import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { createStudioRegistry } from "@haios/command-system";
import { planToCommands } from "../src/compiler.js";

describe("AI caption compilation", () => {
  it("routes add_caption to canonical caption.place", () => {
    const project = createEmptyProject("x", "p1");
    const commands = planToCommands({
      version: 1,
      target: { kind: "selection" },
      operations: [{ tool: "add_caption", params: { text: "Hello" } }],
    }, project, createStudioRegistry());
    expect(commands).toEqual([{ commandType: "caption.place", payload: { text: "Hello" } }]);
  });
});
