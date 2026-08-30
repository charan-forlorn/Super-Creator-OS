import { describe, it, expect } from "vitest";
import {
  OfflineProvider,
  OllamaProvider,
  OpenAICompatibleProvider,
  ProviderUnavailableError,
  modelTextToPlan,
  extractJsonObject,
} from "../src/index.js";

describe("ai-providers", () => {
  it("offline provider routes 'split at 4 seconds' to a split plan", async () => {
    const p = new OfflineProvider();
    const r = await p.generate({
      instruction: "Split the selected clip at 4 seconds",
      context: { clipIds: ["c1"], selectedClipId: "c1" },
    });
    expect(r.plan.operations[0].tool).toBe("split_clip");
    expect(r.plan.operations[0].params.t).toBe(4);
    expect(r.provider).toBe("hermes");
  });

  it("offline provider routes move/trim/delete/caption/aspect", async () => {
    const p = new OfflineProvider();
    expect((await p.generate({ instruction: "move clip to 2 seconds", context: { clipIds: ["c1"], selectedClipId: "c1" } })).plan.operations[0].tool).toBe("move_clip");
    expect((await p.generate({ instruction: "trim clip at 1 second", context: { clipIds: ["c1"], selectedClipId: "c1" } })).plan.operations[0].tool).toBe("trim_clip");
    expect((await p.generate({ instruction: "delete the clip", context: { clipIds: ["c1"], selectedClipId: "c1" } })).plan.operations[0].tool).toBe("delete_clip");
    expect((await p.generate({ instruction: 'add caption "Hello"', context: { clipIds: [] } })).plan.operations[0].tool).toBe("add_caption");
    expect((await p.generate({ instruction: "change aspect ratio to vertical", context: { clipIds: [] } })).plan.operations[0].tool).toBe("change_aspect_ratio");
  });

  it("extractJsonObject pulls JSON out of prose with code fences", () => {
    const txt = "Sure! Here is the plan:\n```json\n{\"version\":1,\"target\":{\"kind\":\"selection\"},\"operations\":[]}\n```\nHope that helps!";
    const obj = JSON.parse(extractJsonObject(txt));
    expect(obj.version).toBe(1);
  });

  it("modelTextToPlan fails closed on non-JSON garbage", () => {
    expect(() => modelTextToPlan("I will now edit your video by moving things around.", "ollama")).toThrow();
  });

  it("Ollama provider throws ProviderUnavailableError when the endpoint fails", async () => {
    const fakeFetch = async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response;
    const p = new OllamaProvider({ baseUrl: "http://localhost:11434", model: "llama3", fetchImpl: fakeFetch as any });
    await expect(p.generate({ instruction: "x", context: { clipIds: [] } })).rejects.toBeInstanceOf(ProviderUnavailableError);
  });

  it("Ollama provider reports unavailable when the tag endpoint errors", async () => {
    const fakeFetch = (async () => { throw new Error("connrefused"); }) as any;
    const p = new OllamaProvider({ baseUrl: "http://localhost:11434", model: "llama3", fetchImpl: fakeFetch });
    expect(await p.isAvailable()).toBe(false);
  });

  it("OpenAI-compatible provider parses a chat-completions JSON response", async () => {
    const fakeFetch = async (_url: string, init: any) => {
      expect(init.headers.authorization).toContain("Bearer");
      return {
        ok: true,
        status: 200,
        json: async () => ({ choices: [{ message: { content: '{"version":1,"target":{"kind":"selection"},"operations":[{"tool":"split_clip","params":{"t":3}}]}' } }] }),
      } as Response;
    };
    const p = new OpenAICompatibleProvider({ baseUrl: "http://localhost:1234/v1", apiKey: "sk-test", model: "local", fetchImpl: fakeFetch as any });
    const r = await p.generate({ instruction: "split at 3", context: { clipIds: ["c1"], selectedClipId: "c1" } });
    expect(r.plan.operations[0].params.t).toBe(3);
  });
});
