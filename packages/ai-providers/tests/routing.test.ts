import { describe, expect, it } from "vitest";
import { evaluateRouteCandidate, type RouteCandidate } from "../src/index.js";

const baseCandidate = (): RouteCandidate => ({
  capability: "generate_image",
  availability: "READY",
  providerId: "provider.local",
  modelId: "model.local",
  costClass: "local_zero_inference_cost",
  health: "HEALTHY",
  currentness: "CURRENT",
  qualification: "QUALIFIED",
  licence: "ALLOWED",
  hardware: "FIT",
  evidenceComplete: true,
});

describe("fail-closed capability route admission", () => {
  it("admits a fully eligible candidate", () => {
    expect(evaluateRouteCandidate(baseCandidate())).toEqual({ eligible: true });
  });

  it("rejects unknown cost before execution", () => {
    expect(evaluateRouteCandidate({ ...baseCandidate(), costClass: "unknown" })).toEqual({ eligible: false, reason: "unknown_cost" });
  });

  it("rejects stale currentness", () => {
    expect(evaluateRouteCandidate({ ...baseCandidate(), currentness: "STALE" })).toEqual({ eligible: false, reason: "stale_currentness" });
  });

  it("rejects unqualified providers", () => {
    expect(evaluateRouteCandidate({ ...baseCandidate(), qualification: "UNQUALIFIED" })).toEqual({ eligible: false, reason: "unqualified" });
  });

  it("rejects candidates without evidence", () => {
    expect(evaluateRouteCandidate({ ...baseCandidate(), evidenceComplete: false })).toEqual({ eligible: false, reason: "missing_evidence" });
  });
});
