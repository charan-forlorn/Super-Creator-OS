import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TrackLabelControls, TrackTargetToolbar } from "../src/components/Timeline.js";

describe("P4.5 track operations UI", () => {
  it("renders target selection, controls, and track operation actions", () => {
    const toolbar = renderToStaticMarkup(React.createElement(TrackTargetToolbar, {
      selectedTrackId: "a1", onAdd: () => {}, onRemove: () => {}, onMove: () => {},
    }));
    expect(toolbar).toContain('data-testid="track-add-video"');
    expect(toolbar).toContain('data-testid="track-add-audio"');
    expect(toolbar).toContain('data-testid="track-add-text"');
    expect(toolbar).toContain('data-testid="track-remove-selected"');
    expect(toolbar).toContain('data-testid="track-move-up"');
    expect(toolbar).toContain('data-testid="track-move-down"');
    expect(toolbar).toContain('data-testid="selected-track-target"');
    expect(toolbar).toContain('Target: a1');

    const row = renderToStaticMarkup(React.createElement(TrackLabelControls, {
      track: { id: "a1", kind: "audio", visible: true, muted: true, locked: true },
      selected: true, onSelect: () => {}, onControls: () => {},
    }));
    expect(row).toContain('data-testid="track-select-a1"');
    expect(row).toContain('data-selected="true"');
    expect(row).toContain('data-testid="track-visible-a1"');
    expect(row).toContain('data-testid="track-muted-a1"');
    expect(row).toContain('data-testid="track-locked-a1"');
  });
});
