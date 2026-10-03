import { describe, expect, it } from "vitest";
import {
  routeCapability,
  type GovernanceEvidence,
  type MachineCapabilityEvidence,
  type RouteCandidate,
} from "../src/index.js";

const governance = (): GovernanceEvidence => ({
  currentness: "CURRENT",
  qualification: "QUALIFIED",
  licence: "ALLOWED",
  hardware: "FIT",
  allowedCostClasses: ["local_zero_inference_cost", "free_keyless"],
  evidenceComplete: true,
  evidenceRefs: ["haios:r6:qualified:1"],
});

const machine = (modelId = "qwen3:4b"): MachineCapabilityEvidence => ({
  observedAt: "2026-09-16T01:00:00.000Z",
  providerId: "ollama",
  providerReachable: true,
  modelId,
  modelPresent: true,
  evidenceRefs: ["machine:ollama:tags:1"],
});

const candidate = (overrides: Partial<RouteCandidate> = {}): RouteCandidate => ({
  capability: "generate_text",
  providerId: "ollama",
  modelId: "qwen3:4b",
  costClass: "local_zero_inference_cost",
  availability: "READY",
  currentness: "CURRENT",
  health: "HEALTHY",
  qualification: "QUALIFIED",
  licence: "ALLOWED",
  hardware: "FIT",
  evidenceComplete: true,
  priority: 100,
  ...overrides,
});

describe("adaptive capability routing", () => {
  it("binds a route to matching machine evidence and HAIOS policy", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate()],
      machineEvidence: [machine()],
      governanceEvidence: { ollama: governance() },
    });
    expect(result.kind).toBe("ROUTED");
    if (result.kind !== "ROUTED") throw new Error("expected route");
    expect(result.candidate.providerId).toBe("ollama");
    expect(result.evidenceRefs).toEqual(["haios:r6:qualified:1", "machine:ollama:tags:1"]);
  });

  it("rejects a model that is not observed on the machine", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate()],
      machineEvidence: [machine("qwen3:14b")],
      governanceEvidence: { ollama: governance() },
    });
    expect(result.kind).toBe("DENIED");
    if (result.kind !== "DENIED") throw new Error("expected denial");
    expect(result.rejections[0].reason).toBe("machine_model_not_observed");
  });
  it("rejects when HAIOS does not provide complete governance evidence", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate()],
      machineEvidence: [machine()],
      governanceEvidence: {},
    });
    expect(result.kind).toBe("DENIED");
    if (result.kind !== "DENIED") throw new Error("expected denial");
    expect(result.rejections[0].reason).toBe("missing_governance_evidence");
  });

  it("chooses the highest-priority eligible candidate deterministically", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [
        candidate({ providerId: "ollama", modelId: "qwen3:4b", priority: 100 }),
        candidate({ providerId: "ollama", modelId: "qwen3:14b", priority: 200 }),
      ],
      machineEvidence: [machine("qwen3:4b"), machine("qwen3:14b")],
      governanceEvidence: { ollama: governance() },
    });
    expect(result.kind).toBe("ROUTED");
    if (result.kind !== "ROUTED") throw new Error("expected route");
    expect(result.candidate.modelId).toBe("qwen3:14b");
  });
  it("fails closed when every candidate is rejected", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate({ health: "UNKNOWN" })],
      machineEvidence: [machine()],
      governanceEvidence: { ollama: governance() },
    });
    expect(result).toEqual({
      kind: "DENIED",
      reason: "no_eligible_route",
      rejections: [{ providerId: "ollama", modelId: "qwen3:4b", reason: "unknown_health" }],
    });
  });

  it("rejects when the observed model digest differs from the candidate version", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate({ modelVersion: "sha256:expected" })],
      machineEvidence: [machine()],
      governanceEvidence: { ollama: governance() },
    });
    expect(result.kind).toBe("DENIED");
    if (result.kind !== "DENIED") throw new Error("expected denial");
    expect(result.rejections[0].reason).toBe("machine_model_version_mismatch");
  });

  it("honors an explicit HAIOS cost policy", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate({ costClass: "free_or_variable" })],
      machineEvidence: [machine()],
      governanceEvidence: { ollama: { ...governance(), allowedCostClasses: ["free_or_variable"] } },
    });
    expect(result.kind).toBe("ROUTED");
  });
});

  it("does not trust candidate governance states over HAIOS evidence", () => {
    const result = routeCapability({
      capability: "generate_text",
      candidates: [candidate({
        currentness: "CURRENT",
        qualification: "QUALIFIED",
        licence: "ALLOWED",
        hardware: "FIT",
      })],
      machineEvidence: [machine()],
      governanceEvidence: {
        ollama: {
          ...governance(),
          currentness: "UNKNOWN",
          qualification: "UNQUALIFIED",
        },
      },
    });
    expect(result.kind).toBe("DENIED");
    if (result.kind !== "DENIED") throw new Error("expected denial");
    expect(result.rejections[0].reason).toBe("unknown_currentness");
  });
