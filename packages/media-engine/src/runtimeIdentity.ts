export type RuntimeToolKind = "ffmpeg" | "ffprobe" | "hyperframes" | "node" | "chrome" | "python";
export type RuntimeResolution = "RESOLVED" | "UNKNOWN";
export type RuntimeIdentityComparison = "MATCH" | "DIFFERENT" | "UNKNOWN";

export interface RuntimeToolIdentity {
  readonly name: RuntimeToolKind;
  readonly path: string;
  readonly version: string;
  readonly resolution: RuntimeResolution;
}

export interface RuntimeIdentity {
  readonly tools: readonly RuntimeToolIdentity[];
}

function toolKey(tool: RuntimeToolIdentity): string {
  return [tool.name, tool.path, tool.version].join("|");
}

export function compareRuntimeIdentity(a: RuntimeIdentity, b: RuntimeIdentity): RuntimeIdentityComparison {
  const all = [...a.tools, ...b.tools];
  if (all.some((tool) => tool.resolution === "UNKNOWN")) return "UNKNOWN";
  if (a.tools.length !== b.tools.length) return "DIFFERENT";

  const left = a.tools.map(toolKey).sort();
  const right = b.tools.map(toolKey).sort();
  return left.every((value, index) => value === right[index]) ? "MATCH" : "DIFFERENT";
}
