import { z } from "zod";
/**
 * Versioned project schema. Bump CURRENT_PROJECT_SCHEMA_VERSION when the
 * persisted shape changes. Old versions are rejected fail-closed unless an
 * explicit migration exists.
 */
export declare const PROJECT_SCHEMA_VERSION: 1;
declare const rationalSchema: z.ZodObject<{
    num: z.ZodNumber;
    den: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    num: number;
    den: number;
}, {
    num: number;
    den: number;
}>;
export type Rational = z.infer<typeof rationalSchema>;
export declare const mediaAssetSchema: z.ZodObject<{
    id: z.ZodString;
    name: z.ZodString;
    /** Absolute or workspace-relative path to the ORIGINAL media. Immutable. */
    sourcePath: z.ZodString;
    kind: z.ZodEnum<["video", "audio", "image"]>;
    durationSec: z.ZodNumber;
    width: z.ZodOptional<z.ZodNumber>;
    height: z.ZodOptional<z.ZodNumber>;
    fps: z.ZodOptional<z.ZodNumber>;
    hasAudio: z.ZodDefault<z.ZodBoolean>;
    /** content hash (sha256) of the original bytes — proves source immutability. */
    checksum: z.ZodOptional<z.ZodString>;
    createdAt: z.ZodString;
}, "strip", z.ZodTypeAny, {
    id: string;
    name: string;
    sourcePath: string;
    kind: "video" | "audio" | "image";
    durationSec: number;
    hasAudio: boolean;
    createdAt: string;
    width?: number | undefined;
    height?: number | undefined;
    fps?: number | undefined;
    checksum?: string | undefined;
}, {
    id: string;
    name: string;
    sourcePath: string;
    kind: "video" | "audio" | "image";
    durationSec: number;
    createdAt: string;
    width?: number | undefined;
    height?: number | undefined;
    fps?: number | undefined;
    hasAudio?: boolean | undefined;
    checksum?: string | undefined;
}>;
export type MediaAsset = z.infer<typeof mediaAssetSchema>;
export declare const clipSchema: z.ZodObject<{
    id: z.ZodString;
    assetId: z.ZodString;
    /** In-point into the SOURCE asset, seconds. */
    inPoint: z.ZodNumber;
    /** Visible duration of this clip on the timeline, seconds. */
    duration: z.ZodNumber;
    /** Position on the timeline track, seconds. */
    start: z.ZodNumber;
    trackId: z.ZodString;
    /** Optional transform for preview/export. */
    transform: z.ZodDefault<z.ZodObject<{
        scale: z.ZodDefault<z.ZodNumber>;
        x: z.ZodDefault<z.ZodNumber>;
        y: z.ZodDefault<z.ZodNumber>;
        opacity: z.ZodDefault<z.ZodNumber>;
    }, "strip", z.ZodTypeAny, {
        scale: number;
        x: number;
        y: number;
        opacity: number;
    }, {
        scale?: number | undefined;
        x?: number | undefined;
        y?: number | undefined;
        opacity?: number | undefined;
    }>>;
    /** Clip-local audio controls; defaults preserve source audio for legacy projects. */
    audio: z.ZodDefault<z.ZodObject<{
        gainDb: z.ZodDefault<z.ZodNumber>;
        muted: z.ZodDefault<z.ZodBoolean>;
    }, "strip", z.ZodTypeAny, {
        gainDb: number;
        muted: boolean;
    }, {
        gainDb?: number | undefined;
        muted?: boolean | undefined;
    }>>;
}, "strip", z.ZodTypeAny, {
    id: string;
    audio: {
        gainDb: number;
        muted: boolean;
    };
    assetId: string;
    inPoint: number;
    duration: number;
    start: number;
    trackId: string;
    transform: {
        scale: number;
        x: number;
        y: number;
        opacity: number;
    };
}, {
    id: string;
    assetId: string;
    inPoint: number;
    duration: number;
    start: number;
    trackId: string;
    audio?: {
        gainDb?: number | undefined;
        muted?: boolean | undefined;
    } | undefined;
    transform?: {
        scale?: number | undefined;
        x?: number | undefined;
        y?: number | undefined;
        opacity?: number | undefined;
    } | undefined;
}>;
export type Clip = z.infer<typeof clipSchema>;
export declare const captionSchema: z.ZodObject<{
    id: z.ZodString;
    /** Track-local caption text (never executed as code). */
    text: z.ZodString;
    /** Visible window on the timeline, seconds. */
    start: z.ZodNumber;
    duration: z.ZodNumber;
    trackId: z.ZodString;
    style: z.ZodDefault<z.ZodObject<{
        fontSizePx: z.ZodDefault<z.ZodNumber>;
        color: z.ZodDefault<z.ZodString>;
        backgroundColor: z.ZodDefault<z.ZodString>;
        backgroundOpacity: z.ZodDefault<z.ZodNumber>;
        x: z.ZodDefault<z.ZodNumber>;
        y: z.ZodDefault<z.ZodNumber>;
    }, "strip", z.ZodTypeAny, {
        x: number;
        y: number;
        fontSizePx: number;
        color: string;
        backgroundColor: string;
        backgroundOpacity: number;
    }, {
        x?: number | undefined;
        y?: number | undefined;
        fontSizePx?: number | undefined;
        color?: string | undefined;
        backgroundColor?: string | undefined;
        backgroundOpacity?: number | undefined;
    }>>;
}, "strip", z.ZodTypeAny, {
    id: string;
    duration: number;
    start: number;
    trackId: string;
    text: string;
    style: {
        x: number;
        y: number;
        fontSizePx: number;
        color: string;
        backgroundColor: string;
        backgroundOpacity: number;
    };
}, {
    id: string;
    duration: number;
    start: number;
    trackId: string;
    text: string;
    style?: {
        x?: number | undefined;
        y?: number | undefined;
        fontSizePx?: number | undefined;
        color?: string | undefined;
        backgroundColor?: string | undefined;
        backgroundOpacity?: number | undefined;
    } | undefined;
}>;
export type Caption = z.infer<typeof captionSchema>;
export declare const trackSchema: z.ZodObject<{
    id: z.ZodString;
    kind: z.ZodEnum<["video", "audio", "text"]>;
    clips: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        assetId: z.ZodString;
        /** In-point into the SOURCE asset, seconds. */
        inPoint: z.ZodNumber;
        /** Visible duration of this clip on the timeline, seconds. */
        duration: z.ZodNumber;
        /** Position on the timeline track, seconds. */
        start: z.ZodNumber;
        trackId: z.ZodString;
        /** Optional transform for preview/export. */
        transform: z.ZodDefault<z.ZodObject<{
            scale: z.ZodDefault<z.ZodNumber>;
            x: z.ZodDefault<z.ZodNumber>;
            y: z.ZodDefault<z.ZodNumber>;
            opacity: z.ZodDefault<z.ZodNumber>;
        }, "strip", z.ZodTypeAny, {
            scale: number;
            x: number;
            y: number;
            opacity: number;
        }, {
            scale?: number | undefined;
            x?: number | undefined;
            y?: number | undefined;
            opacity?: number | undefined;
        }>>;
        /** Clip-local audio controls; defaults preserve source audio for legacy projects. */
        audio: z.ZodDefault<z.ZodObject<{
            gainDb: z.ZodDefault<z.ZodNumber>;
            muted: z.ZodDefault<z.ZodBoolean>;
        }, "strip", z.ZodTypeAny, {
            gainDb: number;
            muted: boolean;
        }, {
            gainDb?: number | undefined;
            muted?: boolean | undefined;
        }>>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        audio: {
            gainDb: number;
            muted: boolean;
        };
        assetId: string;
        inPoint: number;
        duration: number;
        start: number;
        trackId: string;
        transform: {
            scale: number;
            x: number;
            y: number;
            opacity: number;
        };
    }, {
        id: string;
        assetId: string;
        inPoint: number;
        duration: number;
        start: number;
        trackId: string;
        audio?: {
            gainDb?: number | undefined;
            muted?: boolean | undefined;
        } | undefined;
        transform?: {
            scale?: number | undefined;
            x?: number | undefined;
            y?: number | undefined;
            opacity?: number | undefined;
        } | undefined;
    }>, "many">;
    captions: z.ZodDefault<z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        /** Track-local caption text (never executed as code). */
        text: z.ZodString;
        /** Visible window on the timeline, seconds. */
        start: z.ZodNumber;
        duration: z.ZodNumber;
        trackId: z.ZodString;
        style: z.ZodDefault<z.ZodObject<{
            fontSizePx: z.ZodDefault<z.ZodNumber>;
            color: z.ZodDefault<z.ZodString>;
            backgroundColor: z.ZodDefault<z.ZodString>;
            backgroundOpacity: z.ZodDefault<z.ZodNumber>;
            x: z.ZodDefault<z.ZodNumber>;
            y: z.ZodDefault<z.ZodNumber>;
        }, "strip", z.ZodTypeAny, {
            x: number;
            y: number;
            fontSizePx: number;
            color: string;
            backgroundColor: string;
            backgroundOpacity: number;
        }, {
            x?: number | undefined;
            y?: number | undefined;
            fontSizePx?: number | undefined;
            color?: string | undefined;
            backgroundColor?: string | undefined;
            backgroundOpacity?: number | undefined;
        }>>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        duration: number;
        start: number;
        trackId: string;
        text: string;
        style: {
            x: number;
            y: number;
            fontSizePx: number;
            color: string;
            backgroundColor: string;
            backgroundOpacity: number;
        };
    }, {
        id: string;
        duration: number;
        start: number;
        trackId: string;
        text: string;
        style?: {
            x?: number | undefined;
            y?: number | undefined;
            fontSizePx?: number | undefined;
            color?: string | undefined;
            backgroundColor?: string | undefined;
            backgroundOpacity?: number | undefined;
        } | undefined;
    }>, "many">>;
}, "strip", z.ZodTypeAny, {
    id: string;
    kind: "video" | "audio" | "text";
    clips: {
        id: string;
        audio: {
            gainDb: number;
            muted: boolean;
        };
        assetId: string;
        inPoint: number;
        duration: number;
        start: number;
        trackId: string;
        transform: {
            scale: number;
            x: number;
            y: number;
            opacity: number;
        };
    }[];
    captions: {
        id: string;
        duration: number;
        start: number;
        trackId: string;
        text: string;
        style: {
            x: number;
            y: number;
            fontSizePx: number;
            color: string;
            backgroundColor: string;
            backgroundOpacity: number;
        };
    }[];
}, {
    id: string;
    kind: "video" | "audio" | "text";
    clips: {
        id: string;
        assetId: string;
        inPoint: number;
        duration: number;
        start: number;
        trackId: string;
        audio?: {
            gainDb?: number | undefined;
            muted?: boolean | undefined;
        } | undefined;
        transform?: {
            scale?: number | undefined;
            x?: number | undefined;
            y?: number | undefined;
            opacity?: number | undefined;
        } | undefined;
    }[];
    captions?: {
        id: string;
        duration: number;
        start: number;
        trackId: string;
        text: string;
        style?: {
            x?: number | undefined;
            y?: number | undefined;
            fontSizePx?: number | undefined;
            color?: string | undefined;
            backgroundColor?: string | undefined;
            backgroundOpacity?: number | undefined;
        } | undefined;
    }[] | undefined;
}>;
export type Track = z.infer<typeof trackSchema>;
export declare const exportResolutionSchema: z.ZodEnum<["1920x1080", "1080x1920", "1080x1080"]>;
export type ExportResolution = z.infer<typeof exportResolutionSchema>;
export declare const projectSchema: z.ZodObject<{
    schemaVersion: z.ZodNumber;
    id: z.ZodString;
    name: z.ZodString;
    createdAt: z.ZodString;
    updatedAt: z.ZodString;
    assets: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        name: z.ZodString;
        /** Absolute or workspace-relative path to the ORIGINAL media. Immutable. */
        sourcePath: z.ZodString;
        kind: z.ZodEnum<["video", "audio", "image"]>;
        durationSec: z.ZodNumber;
        width: z.ZodOptional<z.ZodNumber>;
        height: z.ZodOptional<z.ZodNumber>;
        fps: z.ZodOptional<z.ZodNumber>;
        hasAudio: z.ZodDefault<z.ZodBoolean>;
        /** content hash (sha256) of the original bytes — proves source immutability. */
        checksum: z.ZodOptional<z.ZodString>;
        createdAt: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        id: string;
        name: string;
        sourcePath: string;
        kind: "video" | "audio" | "image";
        durationSec: number;
        hasAudio: boolean;
        createdAt: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        checksum?: string | undefined;
    }, {
        id: string;
        name: string;
        sourcePath: string;
        kind: "video" | "audio" | "image";
        durationSec: number;
        createdAt: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        hasAudio?: boolean | undefined;
        checksum?: string | undefined;
    }>, "many">;
    tracks: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        kind: z.ZodEnum<["video", "audio", "text"]>;
        clips: z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            assetId: z.ZodString;
            /** In-point into the SOURCE asset, seconds. */
            inPoint: z.ZodNumber;
            /** Visible duration of this clip on the timeline, seconds. */
            duration: z.ZodNumber;
            /** Position on the timeline track, seconds. */
            start: z.ZodNumber;
            trackId: z.ZodString;
            /** Optional transform for preview/export. */
            transform: z.ZodDefault<z.ZodObject<{
                scale: z.ZodDefault<z.ZodNumber>;
                x: z.ZodDefault<z.ZodNumber>;
                y: z.ZodDefault<z.ZodNumber>;
                opacity: z.ZodDefault<z.ZodNumber>;
            }, "strip", z.ZodTypeAny, {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            }, {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            }>>;
            /** Clip-local audio controls; defaults preserve source audio for legacy projects. */
            audio: z.ZodDefault<z.ZodObject<{
                gainDb: z.ZodDefault<z.ZodNumber>;
                muted: z.ZodDefault<z.ZodBoolean>;
            }, "strip", z.ZodTypeAny, {
                gainDb: number;
                muted: boolean;
            }, {
                gainDb?: number | undefined;
                muted?: boolean | undefined;
            }>>;
        }, "strip", z.ZodTypeAny, {
            id: string;
            audio: {
                gainDb: number;
                muted: boolean;
            };
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
        }, {
            id: string;
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            audio?: {
                gainDb?: number | undefined;
                muted?: boolean | undefined;
            } | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
        }>, "many">;
        captions: z.ZodDefault<z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            /** Track-local caption text (never executed as code). */
            text: z.ZodString;
            /** Visible window on the timeline, seconds. */
            start: z.ZodNumber;
            duration: z.ZodNumber;
            trackId: z.ZodString;
            style: z.ZodDefault<z.ZodObject<{
                fontSizePx: z.ZodDefault<z.ZodNumber>;
                color: z.ZodDefault<z.ZodString>;
                backgroundColor: z.ZodDefault<z.ZodString>;
                backgroundOpacity: z.ZodDefault<z.ZodNumber>;
                x: z.ZodDefault<z.ZodNumber>;
                y: z.ZodDefault<z.ZodNumber>;
            }, "strip", z.ZodTypeAny, {
                x: number;
                y: number;
                fontSizePx: number;
                color: string;
                backgroundColor: string;
                backgroundOpacity: number;
            }, {
                x?: number | undefined;
                y?: number | undefined;
                fontSizePx?: number | undefined;
                color?: string | undefined;
                backgroundColor?: string | undefined;
                backgroundOpacity?: number | undefined;
            }>>;
        }, "strip", z.ZodTypeAny, {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style: {
                x: number;
                y: number;
                fontSizePx: number;
                color: string;
                backgroundColor: string;
                backgroundOpacity: number;
            };
        }, {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style?: {
                x?: number | undefined;
                y?: number | undefined;
                fontSizePx?: number | undefined;
                color?: string | undefined;
                backgroundColor?: string | undefined;
                backgroundOpacity?: number | undefined;
            } | undefined;
        }>, "many">>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        kind: "video" | "audio" | "text";
        clips: {
            id: string;
            audio: {
                gainDb: number;
                muted: boolean;
            };
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
        }[];
        captions: {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style: {
                x: number;
                y: number;
                fontSizePx: number;
                color: string;
                backgroundColor: string;
                backgroundOpacity: number;
            };
        }[];
    }, {
        id: string;
        kind: "video" | "audio" | "text";
        clips: {
            id: string;
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            audio?: {
                gainDb?: number | undefined;
                muted?: boolean | undefined;
            } | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
        }[];
        captions?: {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style?: {
                x?: number | undefined;
                y?: number | undefined;
                fontSizePx?: number | undefined;
                color?: string | undefined;
                backgroundColor?: string | undefined;
                backgroundOpacity?: number | undefined;
            } | undefined;
        }[] | undefined;
    }>, "many">;
    /** Duration of the composed timeline, seconds. */
    durationSec: z.ZodNumber;
    /** Output aspect ratio preset for export. */
    aspectRatio: z.ZodDefault<z.ZodEnum<["1920x1080", "1080x1920", "1080x1080"]>>;
}, "strip", z.ZodTypeAny, {
    id: string;
    name: string;
    durationSec: number;
    createdAt: string;
    schemaVersion: number;
    updatedAt: string;
    assets: {
        id: string;
        name: string;
        sourcePath: string;
        kind: "video" | "audio" | "image";
        durationSec: number;
        hasAudio: boolean;
        createdAt: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        checksum?: string | undefined;
    }[];
    tracks: {
        id: string;
        kind: "video" | "audio" | "text";
        clips: {
            id: string;
            audio: {
                gainDb: number;
                muted: boolean;
            };
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
        }[];
        captions: {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style: {
                x: number;
                y: number;
                fontSizePx: number;
                color: string;
                backgroundColor: string;
                backgroundOpacity: number;
            };
        }[];
    }[];
    aspectRatio: "1920x1080" | "1080x1920" | "1080x1080";
}, {
    id: string;
    name: string;
    durationSec: number;
    createdAt: string;
    schemaVersion: number;
    updatedAt: string;
    assets: {
        id: string;
        name: string;
        sourcePath: string;
        kind: "video" | "audio" | "image";
        durationSec: number;
        createdAt: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        hasAudio?: boolean | undefined;
        checksum?: string | undefined;
    }[];
    tracks: {
        id: string;
        kind: "video" | "audio" | "text";
        clips: {
            id: string;
            assetId: string;
            inPoint: number;
            duration: number;
            start: number;
            trackId: string;
            audio?: {
                gainDb?: number | undefined;
                muted?: boolean | undefined;
            } | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
        }[];
        captions?: {
            id: string;
            duration: number;
            start: number;
            trackId: string;
            text: string;
            style?: {
                x?: number | undefined;
                y?: number | undefined;
                fontSizePx?: number | undefined;
                color?: string | undefined;
                backgroundColor?: string | undefined;
                backgroundOpacity?: number | undefined;
            } | undefined;
        }[] | undefined;
    }[];
    aspectRatio?: "1920x1080" | "1080x1920" | "1080x1080" | undefined;
}>;
export type Project = z.infer<typeof projectSchema>;
/** Reject any persisted project whose schemaVersion is not the current one. */
export declare function parseProject(raw: unknown): Project;
export {};
//# sourceMappingURL=schema.d.ts.map