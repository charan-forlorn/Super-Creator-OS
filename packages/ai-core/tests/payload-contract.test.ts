import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, createStudioRegistry, PLACE_CAPTION, CHANGE_ASPECT } from "@haios/command-system";
import { planToCommands } from "../src/compiler.js";

/**
 * Regression coverage for the two REAL payload-contract defects observed in
 * evidence/production-loop/ (3 FAILED governed runs on 2026-09-18):
 *
 *  f6ff926d-2824-4d21-90c1-dd6c198274fe.json
 *    caption.place  -> payload validation failed: invalid_type, expected number,
 *                      received string, path ["duration"]
 *  f54fbced-d680-47f8-aa88-1c57b56dd899.json
 *    project.changeAspect -> payload validation failed: expected
 *                      "'1920x1080' | '1080x1920' | '1080x1080'", received
 *                      undefined, path ["ratio"]
 *  abadc93c-b793-498b-87ea-cd72a11e4eef.json
 *    malformed AI plan: invalid_union at ["operations",N,"params","place"]
 *    (producer-side: the tool param schema admitted only scalars)
 *
 * The defects live in the AI-tool-params -> command-payload contract seam, not
 * in the command schemas themselves. These tests pin the contract so a model
 * emitting numeric strings, or naming the ratio param differently, still
 * produces a payload the CommandBus accepts.
 */
describe("AI payload contract regression (production-loop defects)", () => {
  it("coerces numeric-string caption params into the caption.place payload", () => {
    const project = createEmptyProject("x", "p-cap");
    const commands = planToCommands(
      {
        version: 1,
        target: { kind: "selection" },
        operations: [
          { tool: "add_caption", params: { text: "Hi", start: "2", duration: "3.5" } },
        ],
      },
      project,
      createStudioRegistry(),
    );

    expect(commands).toEqual([
      { commandType: "caption.place", payload: { text: "Hi", start: 2, duration: 3.5 } },
    ]);

    // And the payload must actually execute against the real CommandBus: the
    // bus re-validates against placeCaptionSchema, which is exactly where the
    // production run failed.
    const bus = createCommandBus(project);
    expect(() => bus.execute(commands[0].commandType, commands[0].payload)).not.toThrow();
    expect(bus.project.tracks[0].captions[0]).toMatchObject({
      text: "Hi",
      start: 2,
      duration: 3.5,
    });
  });

  it("accepts a numeric caption payload unchanged (no regression on well-typed input)", () => {
    const project = createEmptyProject("x", "p-cap2");
    const commands = planToCommands(
      {
        version: 1,
        target: { kind: "selection" },
        operations: [{ tool: "add_caption", params: { text: "Hi", start: 1, duration: 2 } }],
      },
      project,
      createStudioRegistry(),
    );
    expect(commands[0].payload).toEqual({ text: "Hi", start: 1, duration: 2 });
  });

  it("accepts an aspect param aliased as 'place' and resolves the ratio", () => {
    // The AI named the param 'place' (an object) instead of 'ratio'. It must be
    // understood rather than dropped, which previously left `ratio` undefined
    // and made the CommandBus reject the command.
    const project = createEmptyProject("x", "p-asp");
    const commands = planToCommands(
      {
        version: 1,
        target: { kind: "selection" },
        operations: [
          { tool: "change_aspect_ratio", params: { place: { ratio: "1080x1920" } } },
        ],
      },
      project,
      createStudioRegistry(),
    );

    expect(commands).toEqual([
      { commandType: "project.changeAspect", payload: { ratio: "1080x1920" } },
    ]);

    const bus = createCommandBus(project);
    expect(() => bus.execute(commands[0].commandType, commands[0].payload)).not.toThrow();
    expect(bus.project.aspectRatio).toBe("1080x1920");
  });

  it("accepts a scalar alias for the aspect ratio and still coerces the value", () => {
    const project = createEmptyProject("x", "p-asp2");
    const commands = planToCommands(
      {
        version: 1,
        target: { kind: "selection" },
        operations: [{ tool: "change_aspect_ratio", params: { aspectRatio: "vertical" } }],
      },
      project,
      createStudioRegistry(),
    );
    expect(commands[0]).toEqual({
      commandType: "project.changeAspect",
      payload: { ratio: "1080x1920" },
    });
  });

  it("keeps the canonical ratio param working with a numeric-looking string", () => {
    const project = createEmptyProject("x", "p-asp3");
    const commands = planToCommands(
      {
        version: 1,
        target: { kind: "selection" },
        operations: [{ tool: "change_aspect_ratio", params: { ratio: "1920x1080" } }],
      },
      project,
      createStudioRegistry(),
    );
    expect(commands[0].payload).toEqual({ ratio: "1920x1080" });
  });

  it("admits a nested object tool param without collapsing to invalid_union", () => {
    // Producer-side defect: `params` was a record of scalars, so a nested
    // object produced a confusing invalid_union over string|number|boolean.
    const project = createEmptyProject("x", "p-nested");
    expect(() =>
      planToCommands(
        {
          version: 1,
          target: { kind: "selection" },
          operations: [
            { tool: "change_aspect_ratio", params: { place: { ratio: "1080x1080" } } },
          ],
        },
        project,
        createStudioRegistry(),
      ),
    ).not.toThrow();
  });

  it("fails closed on an unresolvable aspect ratio rather than inventing one", () => {
    const project = createEmptyProject("x", "p-asp-bad");
    expect(() =>
      planToCommands(
        {
          version: 1,
          target: { kind: "selection" },
          operations: [{ tool: "change_aspect_ratio", params: { place: { ratio: "banana" } } }],
        },
        project,
        createStudioRegistry(),
      ),
    ).toThrow();
  });

  it("fails closed on a non-numeric caption duration", () => {
    const project = createEmptyProject("x", "p-cap-bad");
    expect(() =>
      planToCommands(
        {
          version: 1,
          target: { kind: "selection" },
          operations: [{ tool: "add_caption", params: { text: "Hi", duration: "three" } }],
        },
        project,
        createStudioRegistry(),
      ),
    ).toThrow();
  });
});
