import { z } from "zod";
/**
 * Versioned project schema. Bump CURRENT_PROJECT_SCHEMA_VERSION when the
 * persisted shape changes. Old versions are rejected fail-closed unless an
 * explicit migration exists.
 */
export const PROJECT_SCHEMA_VERSION = 1;
const rationalSchema = z.object({
    num: z.number().int().nonnegative(),
    den: z.number().int().positive(),
});
export const mediaAssetSchema = z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    /** Absolute or workspace-relative path to the ORIGINAL media. Immutable. */
    sourcePath: z.string().min(1),
    kind: z.enum(["video", "audio", "image"]),
    durationSec: z.number().nonnegative(),
    width: z.number().int().nonnegative().optional(),
    height: z.number().int().nonnegative().optional(),
    fps: z.number().positive().optional(),
    hasAudio: z.boolean().default(false),
    /** content hash (sha256) of the original bytes — proves source immutability. */
    checksum: z.string().optional(),
    createdAt: z.string(),
});
export const clipSchema = z.object({
    id: z.string().min(1),
    assetId: z.string().min(1),
    /** In-point into the SOURCE asset, seconds. */
    inPoint: z.number().nonnegative(),
    /** Visible duration of this clip on the timeline, seconds. */
    duration: z.number().positive(),
    /** Position on the timeline track, seconds. */
    start: z.number().nonnegative(),
    trackId: z.string().min(1),
    /** Source playback rate. Timeline duration remains authoritative; source span = duration * playbackRate. */
    playbackRate: z.number().min(0.25).max(4).default(1),
    /** Optional transform for preview/export. */
    transform: z
        .object({
        scale: z.number().positive().default(1),
        x: z.number().default(0),
        y: z.number().default(0),
        opacity: z.number().min(0).max(1).default(1),
    })
        .default({}),
    /** Clip-local visual effects; neutral defaults preserve legacy appearance. */
    effects: z
        .object({
        brightness: z.number().min(-1).max(1).default(0),
        contrast: z.number().min(0).max(2).default(1),
        saturation: z.number().min(0).max(3).default(1),
    })
        .default({}),
    /** Incoming clip transition; null preserves legacy hard-cut behavior. */
    transitionIn: z
        .object({
        type: z.literal("crossfade"),
        duration: z.number().min(0.1).max(2),
    })
        .nullable()
        .default(null),
    /** Clip-local audio controls; defaults preserve source audio for legacy projects. */
    audio: z
        .object({
        gainDb: z.number().min(-60).max(0).default(0),
        muted: z.boolean().default(false),
    })
        .default({}),
});
export const captionSchema = z.object({
    id: z.string().min(1),
    /** Track-local caption text (never executed as code). */
    text: z.string(),
    /** Visible window on the timeline, seconds. */
    start: z.number().nonnegative(),
    duration: z.number().positive(),
    trackId: z.string().min(1),
    style: z
        .object({
        fontSizePx: z.number().positive().default(48),
        color: z.string().default("#FFFFFF"),
        backgroundColor: z.string().default("#000000"),
        backgroundOpacity: z.number().min(0).max(1).default(0.6),
        x: z.number().default(0.5),
        y: z.number().default(0.85),
    })
        .default({}),
});
export const trackSchema = z.object({
    id: z.string().min(1),
    kind: z.enum(["video", "audio", "text"]),
    clips: z.array(clipSchema),
    captions: z.array(captionSchema).default([]),
});
export const exportResolutionSchema = z.enum(["1920x1080", "1080x1920", "1080x1080"]);
export const projectSchema = z.object({
    schemaVersion: z.number().int(),
    id: z.string().min(1),
    name: z.string().min(1),
    createdAt: z.string(),
    updatedAt: z.string(),
    assets: z.array(mediaAssetSchema),
    tracks: z.array(trackSchema),
    /** Duration of the composed timeline, seconds. */
    durationSec: z.number().nonnegative(),
    /** Output aspect ratio preset for export. */
    aspectRatio: exportResolutionSchema.default("1920x1080"),
});
/** Reject any persisted project whose schemaVersion is not the current one. */
export function parseProject(raw) {
    const parsed = projectSchema.safeParse(raw);
    if (!parsed.success) {
        throw new Error(`Invalid project document: ${parsed.error.message}`);
    }
    if (parsed.data.schemaVersion !== PROJECT_SCHEMA_VERSION) {
        throw new Error(`Unsupported project schemaVersion ${parsed.data.schemaVersion}; expected ${PROJECT_SCHEMA_VERSION}`);
    }
    return parsed.data;
}
//# sourceMappingURL=schema.js.map