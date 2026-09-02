import { describe, expect, it } from "vitest";
import { CrossTrackDropIndicator, TrackLabelControls } from "../src/components/Timeline.js";

describe("Phase 5 cross-track timeline feedback", () => {
  it("exposes stable valid and invalid drop feedback", () => {
    expect(CrossTrackDropIndicator({ targetTrackId: "v2", valid: true }).props["data-cross-track-drop"]).toBe("valid");
    expect(CrossTrackDropIndicator({ targetTrackId: "a1", valid: false }).props["data-cross-track-drop"]).toBe("invalid");
    expect(CrossTrackDropIndicator({ targetTrackId: null, valid: false })).toBeNull();
  });

  it("exposes a destination button with the stable per-track test id", () => {
    const element = TrackLabelControls({
      track: { id: "v2", kind: "video", visible: true, muted: false, locked: false }, selected: false,
      onSelect: () => undefined, onControls: () => undefined, canMoveSelection: true, onMoveSelection: () => undefined,
    });
    const children = element.props.children as Array<{ props?: Record<string, unknown> }>;
    expect(children.some((child) => child.props?.["data-testid"] === "track-move-selection-v2" && child.props.disabled === false)).toBe(true);
  });
});
