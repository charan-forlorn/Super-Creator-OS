import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, PLACE_CAPTION } from "../src/index.js";

describe("caption.place", () => {
  it("creates a canonical text track and caption as one undoable edit", () => {
    const bus = createCommandBus(createEmptyProject("x", "p1"));
    bus.execute(PLACE_CAPTION, { text: "Hello", start: 1, duration: 2 });
    expect(bus.project.tracks).toHaveLength(1);
    expect(bus.project.tracks[0].kind).toBe("text");
    expect(bus.project.tracks[0].captions).toHaveLength(1);
    expect(bus.project.tracks[0].captions[0]).toMatchObject({ text: "Hello", start: 1, duration: 2 });
    bus.undo();
    expect(bus.project.tracks).toHaveLength(0);
    bus.redo();
    expect(bus.project.tracks[0].captions[0].text).toBe("Hello");
  });
  it("reuses the canonical text track and derives stable ids", () => {
    const bus = createCommandBus(createEmptyProject("x", "p2"));
    bus.execute(PLACE_CAPTION, { text: "A", start: 0, duration: 1 });
    bus.execute(PLACE_CAPTION, { text: "B", start: 2, duration: 1 });
    expect(bus.project.tracks).toHaveLength(1);
    expect(bus.project.tracks[0].captions.map((c) => c.id)).toEqual(["cap-1", "cap-2"]);
  });

  it("fails closed on empty text or non-positive duration", () => {
    const bus = createCommandBus(createEmptyProject("x", "p3"));
    expect(() => bus.execute(PLACE_CAPTION, { text: "", start: 0, duration: 1 })).toThrow();
    expect(() => bus.execute(PLACE_CAPTION, { text: "x", start: 0, duration: 0 })).toThrow();
    expect(bus.project.tracks).toHaveLength(0);
  });
});
