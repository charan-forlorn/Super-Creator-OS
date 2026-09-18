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
export declare function compareRuntimeIdentity(a: RuntimeIdentity, b: RuntimeIdentity): RuntimeIdentityComparison;
