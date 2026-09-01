import { z } from "zod";
import { type Clip, type MediaAsset } from "@haios/project-model";
import { EditCommand } from "./types.js";
export declare const ADD_ASSET = "asset.add";
export declare const addAssetCommand: EditCommand<{
    asset: MediaAsset;
}>;
export declare const removeAssetCommand: EditCommand<{
    asset: MediaAsset;
}>;
export declare const ADD_CLIP = "clip.add";
export declare const addClipCommand: EditCommand<{
    clip: Clip;
}>;
export declare const DELETE_CLIP = "clip.delete";
export declare const deleteClipCommand: EditCommand<{
    clipId: string;
}>;
export declare const MOVE_CLIP = "clip.move";
export declare const moveClipSchema: z.ZodObject<{
    clipId: z.ZodString;
    newStart: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    newStart: number;
}, {
    clipId: string;
    newStart: number;
}>;
export declare const moveClipCommand: EditCommand<z.infer<typeof moveClipSchema>>;
export declare const SET_CLIP_AUDIO = "clip.audio";
export declare const setClipAudioSchema: z.ZodObject<{
    clipId: z.ZodString;
    gainDb: z.ZodNumber;
    muted: z.ZodBoolean;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    gainDb: number;
    muted: boolean;
}, {
    clipId: string;
    gainDb: number;
    muted: boolean;
}>;
export declare const setClipAudioCommand: EditCommand<z.infer<typeof setClipAudioSchema>>;
export declare const SET_CLIP_EFFECTS = "clip.effects";
export declare const setClipEffectsSchema: z.ZodObject<{
    clipId: z.ZodString;
    brightness: z.ZodNumber;
    contrast: z.ZodNumber;
    saturation: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    brightness: number;
    contrast: number;
    saturation: number;
}, {
    clipId: string;
    brightness: number;
    contrast: number;
    saturation: number;
}>;
export declare const setClipEffectsCommand: EditCommand<z.infer<typeof setClipEffectsSchema>>;
export declare const SET_CLIP_SPEED = "clip.speed";
export declare const setClipSpeedSchema: z.ZodObject<{
    clipId: z.ZodString;
    playbackRate: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    playbackRate: number;
}, {
    clipId: string;
    playbackRate: number;
}>;
export declare const setClipSpeedCommand: EditCommand<z.infer<typeof setClipSpeedSchema>>;
export declare const SET_CLIP_TRANSITION = "clip.transition";
export declare const setClipTransitionSchema: z.ZodObject<{
    clipId: z.ZodString;
    mode: z.ZodEnum<["none", "crossfade"]>;
    duration: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    mode: "crossfade" | "none";
    duration?: number | undefined;
}, {
    clipId: string;
    mode: "crossfade" | "none";
    duration?: number | undefined;
}>;
export declare const setClipTransitionCommand: EditCommand<z.infer<typeof setClipTransitionSchema>>;
export declare const SET_CLIP_TRANSFORM = "clip.transform";
export declare const setClipTransformSchema: z.ZodObject<{
    clipId: z.ZodString;
    scale: z.ZodNumber;
    x: z.ZodNumber;
    y: z.ZodNumber;
    opacity: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    scale: number;
    x: number;
    y: number;
    opacity: number;
}, {
    clipId: string;
    scale: number;
    x: number;
    y: number;
    opacity: number;
}>;
export declare const setClipTransformCommand: EditCommand<z.infer<typeof setClipTransformSchema>>;
export declare const RIPPLE_DELETE_CLIPS = "clip.rippleDelete";
export declare const rippleDeleteClipsSchema: z.ZodObject<{
    clipIds: z.ZodArray<z.ZodString, "many">;
}, "strip", z.ZodTypeAny, {
    clipIds: string[];
}, {
    clipIds: string[];
}>;
export declare const RIPPLE_TRIM_CLIP = "clip.rippleTrim";
export declare const rippleTrimClipSchema: z.ZodObject<{
    clipId: z.ZodString;
    newInPoint: z.ZodOptional<z.ZodNumber>;
    newSourceEnd: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    newInPoint?: number | undefined;
    newSourceEnd?: number | undefined;
}, {
    clipId: string;
    newInPoint?: number | undefined;
    newSourceEnd?: number | undefined;
}>;
export declare const rippleDeleteClipsCommand: EditCommand<z.infer<typeof rippleDeleteClipsSchema>>;
export declare const rippleTrimClipCommand: EditCommand<z.infer<typeof rippleTrimClipSchema>>;
export declare const TRIM_CLIP = "clip.trim";
export declare const trimClipSchema: z.ZodObject<{
    clipId: z.ZodString;
    /** New in-point (trim left). */
    newInPoint: z.ZodOptional<z.ZodNumber>;
    /** New source end (trim right). */
    newSourceEnd: z.ZodOptional<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    newInPoint?: number | undefined;
    newSourceEnd?: number | undefined;
}, {
    clipId: string;
    newInPoint?: number | undefined;
    newSourceEnd?: number | undefined;
}>;
export declare const trimClipCommand: EditCommand<z.infer<typeof trimClipSchema>>;
export declare const PLACE_CAPTION = "caption.place";
export declare const placeCaptionSchema: z.ZodObject<{
    text: z.ZodString;
    start: z.ZodDefault<z.ZodNumber>;
    duration: z.ZodDefault<z.ZodNumber>;
}, "strip", z.ZodTypeAny, {
    text: string;
    duration: number;
    start: number;
}, {
    text: string;
    duration?: number | undefined;
    start?: number | undefined;
}>;
export declare const placeCaptionCommand: EditCommand<z.infer<typeof placeCaptionSchema>>;
export declare const ADD_CAPTION = "caption.add";
export declare const addCaptionSchema: z.ZodObject<{
    caption: z.ZodObject<{
        id: z.ZodString;
        text: z.ZodString;
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
}, "strip", z.ZodTypeAny, {
    caption: {
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
    };
}, {
    caption: {
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
    };
}>;
export declare const addCaptionCommand: EditCommand<z.infer<typeof addCaptionSchema>>;
export declare const REMOVE_CAPTION = "caption.remove";
export declare const removeCaptionCommand: EditCommand<{
    captionId: string;
    trackId: string;
}>;
export declare const CHANGE_ASPECT = "project.changeAspect";
export declare const changeAspectSchema: z.ZodObject<{
    ratio: z.ZodEnum<["1920x1080", "1080x1920", "1080x1080"]>;
}, "strip", z.ZodTypeAny, {
    ratio: "1920x1080" | "1080x1920" | "1080x1080";
}, {
    ratio: "1920x1080" | "1080x1920" | "1080x1080";
}>;
export declare const changeAspectCommand: EditCommand<z.infer<typeof changeAspectSchema>>;
export declare const ADD_TRACK = "track.add";
export declare const addTrackSchema: z.ZodObject<{
    track: z.ZodObject<{
        id: z.ZodString;
        kind: z.ZodEnum<["video", "audio", "text"]>;
        clips: z.ZodDefault<z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            assetId: z.ZodString;
            inPoint: z.ZodNumber;
            duration: z.ZodNumber;
            start: z.ZodNumber;
            trackId: z.ZodString;
            playbackRate: z.ZodDefault<z.ZodNumber>;
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
            effects: z.ZodDefault<z.ZodObject<{
                brightness: z.ZodDefault<z.ZodNumber>;
                contrast: z.ZodDefault<z.ZodNumber>;
                saturation: z.ZodDefault<z.ZodNumber>;
            }, "strip", z.ZodTypeAny, {
                brightness: number;
                contrast: number;
                saturation: number;
            }, {
                brightness?: number | undefined;
                contrast?: number | undefined;
                saturation?: number | undefined;
            }>>;
            transitionIn: z.ZodDefault<z.ZodNullable<z.ZodObject<{
                type: z.ZodLiteral<"crossfade">;
                duration: z.ZodNumber;
            }, "strip", z.ZodTypeAny, {
                type: "crossfade";
                duration: number;
            }, {
                type: "crossfade";
                duration: number;
            }>>>;
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
            playbackRate: number;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
            effects: {
                brightness: number;
                contrast: number;
                saturation: number;
            };
            transitionIn: {
                type: "crossfade";
                duration: number;
            } | null;
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
            playbackRate?: number | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
            effects?: {
                brightness?: number | undefined;
                contrast?: number | undefined;
                saturation?: number | undefined;
            } | undefined;
            transitionIn?: {
                type: "crossfade";
                duration: number;
            } | null | undefined;
        }>, "many">>;
        captions: z.ZodDefault<z.ZodArray<z.ZodObject<{
            id: z.ZodString;
            text: z.ZodString;
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
        visible: z.ZodDefault<z.ZodBoolean>;
        muted: z.ZodDefault<z.ZodBoolean>;
        locked: z.ZodDefault<z.ZodBoolean>;
    }, "strip", z.ZodTypeAny, {
        muted: boolean;
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
            playbackRate: number;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
            effects: {
                brightness: number;
                contrast: number;
                saturation: number;
            };
            transitionIn: {
                type: "crossfade";
                duration: number;
            } | null;
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
        visible: boolean;
        locked: boolean;
    }, {
        id: string;
        kind: "video" | "audio" | "text";
        muted?: boolean | undefined;
        clips?: {
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
            playbackRate?: number | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
            effects?: {
                brightness?: number | undefined;
                contrast?: number | undefined;
                saturation?: number | undefined;
            } | undefined;
            transitionIn?: {
                type: "crossfade";
                duration: number;
            } | null | undefined;
        }[] | undefined;
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
        visible?: boolean | undefined;
        locked?: boolean | undefined;
    }>;
}, "strip", z.ZodTypeAny, {
    track: {
        muted: boolean;
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
            playbackRate: number;
            transform: {
                scale: number;
                x: number;
                y: number;
                opacity: number;
            };
            effects: {
                brightness: number;
                contrast: number;
                saturation: number;
            };
            transitionIn: {
                type: "crossfade";
                duration: number;
            } | null;
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
        visible: boolean;
        locked: boolean;
    };
}, {
    track: {
        id: string;
        kind: "video" | "audio" | "text";
        muted?: boolean | undefined;
        clips?: {
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
            playbackRate?: number | undefined;
            transform?: {
                scale?: number | undefined;
                x?: number | undefined;
                y?: number | undefined;
                opacity?: number | undefined;
            } | undefined;
            effects?: {
                brightness?: number | undefined;
                contrast?: number | undefined;
                saturation?: number | undefined;
            } | undefined;
            transitionIn?: {
                type: "crossfade";
                duration: number;
            } | null | undefined;
        }[] | undefined;
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
        visible?: boolean | undefined;
        locked?: boolean | undefined;
    };
}>;
export declare const addTrackCommand: EditCommand<z.infer<typeof addTrackSchema>>;
export declare const REMOVE_TRACK = "track.remove";
export declare const removeTrackCommand: EditCommand<{
    trackId: string;
}>;
export declare const PLACE_PROBED_MEDIA = "media.placeProbed";
export declare const placeProbedMediaSchema: z.ZodObject<{
    probe: z.ZodObject<{
        id: z.ZodString;
        name: z.ZodString;
        sourcePath: z.ZodString;
        kind: z.ZodEnum<["video", "audio", "image", "unknown"]>;
        durationSec: z.ZodNumber;
        width: z.ZodOptional<z.ZodNumber>;
        height: z.ZodOptional<z.ZodNumber>;
        fps: z.ZodOptional<z.ZodNumber>;
        hasAudio: z.ZodBoolean;
        videoCodec: z.ZodOptional<z.ZodNullable<z.ZodString>>;
        audioCodec: z.ZodOptional<z.ZodNullable<z.ZodString>>;
        probeStatus: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        id: string;
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    }, {
        id: string;
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    }>;
    place: z.ZodDefault<z.ZodBoolean>;
}, "strip", z.ZodTypeAny, {
    probe: {
        id: string;
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    };
    place: boolean;
}, {
    probe: {
        id: string;
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    };
    place?: boolean | undefined;
}>;
export declare const placeProbedMediaCommand: EditCommand<z.infer<typeof placeProbedMediaSchema>>;
export declare const TIMELINE_INSERT_ASSET = "timeline.insertAsset";
export declare const TIMELINE_OVERWRITE_ASSET = "timeline.overwriteAsset";
export declare const timelineAssetEditSchema: z.ZodObject<{
    assetId: z.ZodString;
    clipId: z.ZodString;
    atSec: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    assetId: string;
    atSec: number;
}, {
    clipId: string;
    assetId: string;
    atSec: number;
}>;
type TimelineAssetEdit = z.infer<typeof timelineAssetEditSchema>;
export declare const timelineInsertAssetCommand: EditCommand<TimelineAssetEdit>;
export declare const timelineOverwriteAssetCommand: EditCommand<TimelineAssetEdit>;
export declare const RELINK_MEDIA = "media.relink";
export declare const relinkMediaSchema: z.ZodObject<{
    assetId: z.ZodString;
    probe: z.ZodObject<{
        name: z.ZodString;
        sourcePath: z.ZodString;
        kind: z.ZodEnum<["video", "audio", "image", "unknown"]>;
        durationSec: z.ZodNumber;
        width: z.ZodOptional<z.ZodNumber>;
        height: z.ZodOptional<z.ZodNumber>;
        fps: z.ZodOptional<z.ZodNumber>;
        hasAudio: z.ZodBoolean;
        videoCodec: z.ZodOptional<z.ZodNullable<z.ZodString>>;
        audioCodec: z.ZodOptional<z.ZodNullable<z.ZodString>>;
        probeStatus: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    }, {
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    }>;
}, "strip", z.ZodTypeAny, {
    probe: {
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    };
    assetId: string;
}, {
    probe: {
        kind: "video" | "audio" | "image" | "unknown";
        name: string;
        sourcePath: string;
        durationSec: number;
        hasAudio: boolean;
        probeStatus: string;
        width?: number | undefined;
        height?: number | undefined;
        fps?: number | undefined;
        videoCodec?: string | null | undefined;
        audioCodec?: string | null | undefined;
    };
    assetId: string;
}>;
export declare const relinkMediaCommand: EditCommand<z.infer<typeof relinkMediaSchema>>;
export declare const SPLIT_CLIP = "clip.split";
export declare const splitClipSchema: z.ZodObject<{
    clipId: z.ZodString;
    t: z.ZodNumber;
}, "strip", z.ZodTypeAny, {
    clipId: string;
    t: number;
}, {
    clipId: string;
    t: number;
}>;
export declare const splitClipCommand: EditCommand<z.infer<typeof splitClipSchema>>;
export {};
//# sourceMappingURL=commands.d.ts.map