import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { routeCapability, type RouteCandidate } from "../src/index.js";
import {
  runGovernedProductionLoop,
  type QualificationBinding,
} from "../src/governedProductionLoop.js";
import {
  sealEvidence,
  summarizeModelHistory,
  verifyEvidenceSeal,
  type ProductionEvidence,
} from "../src/productionTelemetry.js";

const binding: QualificationBinding = {
  sourceRepo: "C:/Workspace/hermes-ai-operating-system",
  sourceCommit: "test-qualification-commit",
  sourcePath: "IMPLEMENTATION_BLUEPRINT.md",
  sourceSha256: "test-blueprint-sha",
  models: {
    "qwen3:4b": { digest: "digest-4b", qualification: "QUALIFIED" },
    "qwen3:14b": { digest: "digest-14b", qualification: "QUALIFIED" },
  },
};

describe("production telemetry and governed loop", () => {
  it("seals evidence deterministically from canonical payload bytes", () => {
    const payload = {
      schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1" as const,
      loopRunId: "loop-1",
      routeDecisionId: "route-1",
      observedAt: "2026-09-18T08:00:00.000Z",
      routeDecision: { kind: "ROUTED", model: "qwen3:4b" },
      qualification: {
        sourceRepo: "repo",
        sourceCommit: "commit",
        sourcePath: "path",
        sourceSha256: "sha",
        modelDigest: "digest",
      },
      telemetry: null,
      verification: {
        status: "NOT_RUN" as const,
        planSchemaValidated: false,
      },
    };
    const sealed = sealEvidence(payload);
    expect(sealed.evidenceSha256).toMatch(/^[0-9a-f]{64}$/);
    expect(sealEvidence(payload).evidenceSha256).toBe(sealed.evidenceSha256);
    expect(verifyEvidenceSeal(sealed)).toBe(true);
    const tampered = { ...sealed, routeDecisionId: "tampered" };
    expect(verifyEvidenceSeal(tampered)).toBe(false);
    expect(sealed.loopRunId).toBe("loop-1");
  });

  it("executes a real-shape governed loop against an injected provider transport and joins telemetry by loop_run_id", async () => {
    const evidenceDir = await mkdtemp(join(tmpdir(), "scos-loop-"));
    try {
      const fakeFetch: typeof fetch = async (input, init) => {
        const url = String(input);
        if (url.endsWith("/api/tags")) {
          return new Response(JSON.stringify({
            models: [
              { name: "qwen3:4b", digest: "digest-4b" },
              { name: "qwen3:14b", digest: "digest-14b" },
            ],
          }), { status: 200, headers: { "content-type": "application/json" } });
        }
        const body = JSON.parse(String(init?.body ?? "{}")) as { model?: string };
        await new Promise((resolve) => setTimeout(resolve, body.model === "qwen3:14b" ? 25 : 5));
        return new Response(JSON.stringify({
          response: JSON.stringify({
            version: 1,
            target: { kind: "selection" },
            operations: [{ tool: "change_aspect_ratio", params: { ratio: "1080x1920" } }],
          }),
        }), { status: 200, headers: { "content-type": "application/json" } });
      };

      const first = await runGovernedProductionLoop({
        instruction: "Change the project aspect ratio to vertical.",
        baseUrl: "http://fake-ollama",
        evidenceDir,
        qualification: binding,
        modelOverride: "qwen3:4b",
        fetchImpl: fakeFetch,
      });
      expect(first.status).toBe("COMPLETED");
      expect(first.selectedModel).toBe("qwen3:4b");
      expect(first.telemetry?.loopRunId).toBe(first.loopRunId);

      const second = await runGovernedProductionLoop({
        instruction: "Change the project aspect ratio to vertical.",
        baseUrl: "http://fake-ollama",
        evidenceDir,
        qualification: binding,
        modelOverride: "qwen3:14b",
        fetchImpl: fakeFetch,
      });
      expect(second.status).toBe("COMPLETED");

      const third = await runGovernedProductionLoop({
        instruction: "Change the project aspect ratio to vertical.",
        baseUrl: "http://fake-ollama",
        evidenceDir,
        qualification: binding,
        fetchImpl: fakeFetch,
      });
      expect(third.status).toBe("COMPLETED");
      expect(third.selectedModel).toBe("qwen3:4b");

      const evidence = JSON.parse(
        await readFile(third.evidencePath, "utf8"),
      ) as ProductionEvidence;
      expect(evidence.loopRunId).toBe(third.loopRunId);
      expect(evidence.routeDecision).toHaveProperty("loopRunId", third.loopRunId);
      expect(evidence.telemetry?.routeDecisionId).toBe(third.routeDecisionId);
      expect(evidence.telemetry?.status).toBe("COMPLETED");
      expect(evidence.verification.status).toBe("PASS");
    } finally {
      await rm(evidenceDir, { recursive: true, force: true });
    }
  });

  it("fails closed when qualification evidence is not present on the machine", async () => {
    const evidenceDir = await mkdtemp(join(tmpdir(), "scos-loop-denied-"));
    try {
      const result = await runGovernedProductionLoop({
        instruction: "Change the project aspect ratio to vertical.",
        baseUrl: "http://fake-ollama",
        evidenceDir,
        qualification: {
          ...binding,
          models: {
            "qwen3:4b": { digest: "wrong-digest", qualification: "QUALIFIED" },
          },
        },
        fetchImpl: async () => new Response(JSON.stringify({
          models: [{ name: "qwen3:4b", digest: "digest-4b" }],
        }), { status: 200 }),
      });
      expect(result.status).toBe("DENIED");
      expect(result.telemetry).toBeNull();
      expect(result.error).toBe("no eligible route");
    } finally {
      await rm(evidenceDir, { recursive: true, force: true });
    }
  });

  it("ignores stale telemetry when the generation contract revision changes", () => {
    const rows = [
      {
        schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1" as const,
        loopRunId: "stale",
        routeDecisionId: "route-stale",
        observedAt: "2026-09-18T08:00:00.000Z",
        startedAt: "2026-09-18T08:00:00.000Z",
        completedAt: "2026-09-18T08:00:10.000Z",
        durationMs: 10_000,
        capabilityId: "cap",
        providerId: "ollama",
        modelId: "qwen3:4b",
        status: "FAILED" as const,
        generationStatus: "COMPLETED" as const,
        executionStatus: "FAILED" as const,
        contractRevision: "old-contract",
        requestSha256: "req",
        fallbackUsed: false as const,
        evidenceRefs: ["old"],
      },
      {
        schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1" as const,
        loopRunId: "current",
        routeDecisionId: "route-current",
        observedAt: "2026-09-18T09:00:00.000Z",
        startedAt: "2026-09-18T09:00:00.000Z",
        completedAt: "2026-09-18T09:00:01.000Z",
        durationMs: 1_000,
        capabilityId: "cap",
        providerId: "ollama",
        modelId: "qwen3:4b",
        status: "COMPLETED" as const,
        generationStatus: "COMPLETED" as const,
        executionStatus: "COMPLETED" as const,
        contractRevision: "current-contract",
        requestSha256: "req",
        fallbackUsed: false as const,
        evidenceRefs: ["current"],
      },
    ];
    const history = summarizeModelHistory(rows, "ollama", "qwen3:4b", "current-contract");
    expect(history.successRate).toBe(1);
    expect(history.observedLatencyMs).toBe(1000);
  });

  it("uses observed success and latency only after both routes have real history", () => {
    const base = {
      capability: "generate_text" as const,
      costClass: "local_zero_inference_cost" as const,
      availability: "READY" as const,
      currentness: "CURRENT" as const,
      health: "HEALTHY" as const,
      qualification: "QUALIFIED" as const,
      licence: "ALLOWED" as const,
      hardware: "FIT" as const,
      evidenceComplete: true,
      priority: 0,
    };
    const candidate = (modelId: string, success: number, latency: number): RouteCandidate => ({
      ...base,
      providerId: "ollama",
      modelId,
      observedSuccessRate: success,
      observedLatencyMs: latency,
    });
    const result = routeCapability({
      capability: "generate_text",
      routeDecisionId: "route-1",
      loopRunId: "loop-1",
      candidates: [
        candidate("qwen3:14b", 1, 120),
        candidate("qwen3:4b", 1, 20),
      ],
      machineEvidence: [
        { observedAt: "now", providerId: "ollama", providerReachable: true, modelId: "qwen3:14b", modelPresent: true, evidenceRefs: ["m14"] },
        { observedAt: "now", providerId: "ollama", providerReachable: true, modelId: "qwen3:4b", modelPresent: true, evidenceRefs: ["m4"] },
      ],
      governanceEvidence: {
        "ollama:qwen3:14b": {
          currentness: "CURRENT", qualification: "QUALIFIED", licence: "ALLOWED", hardware: "FIT",
          allowedCostClasses: ["local_zero_inference_cost"], evidenceComplete: true, evidenceRefs: ["g14"],
        },
        "ollama:qwen3:4b": {
          currentness: "CURRENT", qualification: "QUALIFIED", licence: "ALLOWED", hardware: "FIT",
          allowedCostClasses: ["local_zero_inference_cost"], evidenceComplete: true, evidenceRefs: ["g4"],
        },
      },
    });
    expect(result.kind).toBe("ROUTED");
    if (result.kind !== "ROUTED") throw new Error("expected route");
    expect(result.candidate.modelId).toBe("qwen3:4b");
    expect(result.routeDecisionId).toBe("route-1");
    expect(result.loopRunId).toBe("loop-1");
  });
});
