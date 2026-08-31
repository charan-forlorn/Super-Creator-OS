import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

describe("R2.4 caption workspace store", () => {
  beforeEach(() => useStudio.getState().newProject());

  it("places a caption on a fresh project and undo/redo preserves it", () => {
    expect(useStudio.getState().placeCaption("Hello", 1, 2)).toBe(true);
    let captions = useStudio.getState().project.tracks.flatMap((t) => t.captions);
    expect(captions).toHaveLength(1);
    expect(captions[0]).toMatchObject({ text: "Hello", start: 1, duration: 2 });
    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks.flatMap((t) => t.captions)).toHaveLength(0);
    useStudio.getState().redo();
    captions = useStudio.getState().project.tracks.flatMap((t) => t.captions);
    expect(captions[0].text).toBe("Hello");
  });
  it("deletes a caption through the command bus and undo restores it", () => {
    useStudio.getState().placeCaption("Delete me", 0, 3);
    const track = useStudio.getState().project.tracks.find((t) => t.kind === "text")!;
    const caption = track.captions[0];
    expect(useStudio.getState().removeCaption(caption.id, track.id)).toBe(true);
    expect(useStudio.getState().project.tracks.flatMap((t) => t.captions)).toHaveLength(0);
    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks.flatMap((t) => t.captions)[0].text).toBe("Delete me");
  });
});
