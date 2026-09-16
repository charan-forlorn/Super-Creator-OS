import { describe, expect, it } from "vitest";
import { probeOllamaMachineEvidence } from "../src/index.js";

describe("Ollama machine evidence", () => {
  it("records the provider, observed models and healthy probe", async () => {
    const fetchImpl = async () => new Response(JSON.stringify({
      models: [
        { name: "qwen3:4b", digest: "sha256:4b", size: 100 },
        { name: "qwen3:14b", digest: "sha256:14b", size: 200 },
      ],
    }), { status: 200, headers: { "content-type": "application/json" } });
    const result = await probeOllamaMachineEvidence({
      baseUrl: "http://localhost:11434",
      observedAt: "2026-09-16T01:00:00.000Z",
      evidenceRef: "machine:ollama:tags:test",
      fetchImpl,
    });
    expect(result.providerReachable).toBe(true);
    expect(result.health).toBe("HEALTHY");
    expect(result.models).toEqual([
      { modelId: "qwen3:4b", modelVersion: "sha256:4b" },
      { modelId: "qwen3:14b", modelVersion: "sha256:14b" },
    ]);
    expect(result.evidenceRefs).toEqual(["machine:ollama:tags:test"]);
  });

  it("fails closed on an unreachable Ollama endpoint", async () => {
    const fetchImpl = async () => { throw new Error("offline"); };
    const result = await probeOllamaMachineEvidence({
      baseUrl: "http://localhost:11434",
      observedAt: "2026-09-16T01:00:00.000Z",
      evidenceRef: "machine:ollama:tags:offline",
      fetchImpl,
    });
    expect(result.providerReachable).toBe(false);
    expect(result.health).toBe("UNHEALTHY");
    expect(result.models).toEqual([]);
  });
});
