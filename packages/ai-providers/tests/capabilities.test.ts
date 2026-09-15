import { describe, expect, it } from "vitest";
import {
  CAPABILITY_NAMES,
  type CapabilityName,
  evaluateCapabilityCandidate,
  capabilityDescriptorSchema,
} from "../src/index.js";

describe("canonical capability contract", () => {
  it("contains the business-production capability vocabulary", () => {
    const expected: CapabilityName[] = [
      "generate_text",
      "generate_image",
      "edit_image",
      "generate_video",
      "image_to_video",
      "generate_voice",
      "generate_music",
      "transcribe",
      "remove_background",
      "upscale",
      "analyze_media",
      "edit_video",
      "compose_video",
      "render_video",
    ];
    expect([...CAPABILITY_NAMES]).toEqual(expected);
  });

  it("validates a provider-neutral capability descriptor", () => {
    const descriptor = capabilityDescriptorSchema.parse({
      capability: "generate_image",
      provider: { id: "provider.local", kind: "local" },
      model: { id: "model.example", version: "1" },
      costClass: "local_zero_inference_cost",
      availability: "READY",
    });
    expect(descriptor.capability).toBe("generate_image");
  });

  it("rejects unknown cost as ineligible", () => {
    const result = evaluateCapabilityCandidate({
      capability: "generate_video",
      costClass: "unknown",
      availability: "READY",
      currentness: "CURRENT",
      health: "HEALTHY",
      qualification: "QUALIFIED",
      licence: "ALLOWED",
      hardware: "FIT",
      evidenceComplete: true,
    });
    expect(result).toEqual({ eligible: false, reason: "unknown_cost" });
  });

  it("does not let capability metadata create execution authority", () => {
    const result = evaluateCapabilityCandidate({
      capability: "render_video",
      costClass: "local_zero_inference_cost",
      availability: "READY",
      currentness: "CURRENT",
      health: "HEALTHY",
      qualification: "QUALIFIED",
      licence: "ALLOWED",
      hardware: "FIT",
      evidenceComplete: true,
    });
    expect(result).toEqual({ eligible: true });
    expect("authorized" in result).toBe(false);
  });
});
