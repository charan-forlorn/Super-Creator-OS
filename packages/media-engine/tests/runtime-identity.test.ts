import { describe, expect, it } from "vitest";
import {
  compareRuntimeIdentity,
  type RuntimeIdentity,
  type RuntimeToolIdentity,
} from "../src/index.js";

const tool = (path: string, version = "1"): RuntimeToolIdentity => ({
  name: "ffmpeg",
  path,
  version,
  resolution: "RESOLVED",
});

describe("media runtime identity", () => {
  it("treats the canonical absolute path as identity", () => {
    const a: RuntimeIdentity = { tools: [tool("C:\\tools\\ffmpeg.exe", "8.1.2")] };
    const b: RuntimeIdentity = { tools: [tool("C:\\other\\ffmpeg.exe", "8.1.2")] };
    expect(compareRuntimeIdentity(a, b)).toBe("DIFFERENT");
  });

  it("does not treat an unresolved tool as usable identity", () => {
    const a: RuntimeIdentity = {
      tools: [{ ...tool(""), resolution: "UNKNOWN" }],
    };
    const b: RuntimeIdentity = { tools: [tool("C:\\tools\\ffmpeg.exe")] };
    expect(compareRuntimeIdentity(a, b)).toBe("UNKNOWN");
  });

  it("returns MATCH only when all tool identities match", () => {
    const a: RuntimeIdentity = { tools: [tool("C:\\tools\\ffmpeg.exe", "8.1.2")] };
    const b: RuntimeIdentity = { tools: [tool("C:\\tools\\ffmpeg.exe", "8.1.2")] };
    expect(compareRuntimeIdentity(a, b)).toBe("MATCH");
  });
});
