import { z } from "zod";
export declare const CAPABILITY_NAMES: readonly ["generate_text", "generate_image", "edit_image", "generate_video", "image_to_video", "generate_voice", "generate_music", "transcribe", "remove_background", "upscale", "analyze_media", "edit_video", "compose_video", "render_video"];
export type CapabilityName = (typeof CAPABILITY_NAMES)[number];
export declare const CAPABILITY_AVAILABILITIES: readonly ["READY", "PARTIAL", "ADAPTER_ONLY", "EXTERNAL", "LOCAL_NO_MODEL", "PLANNED", "BLOCKED", "UNKNOWN"];
export type CapabilityAvailability = (typeof CAPABILITY_AVAILABILITIES)[number];
export declare const COST_CLASSES: readonly ["local_zero_inference_cost", "free_keyless", "free_or_variable", "paid", "unknown"];
export type CostClass = (typeof COST_CLASSES)[number];
export declare const capabilityDescriptorSchema: z.ZodObject<{
    capability: z.ZodEnum<["generate_text", "generate_image", "edit_image", "generate_video", "image_to_video", "generate_voice", "generate_music", "transcribe", "remove_background", "upscale", "analyze_media", "edit_video", "compose_video", "render_video"]>;
    provider: z.ZodObject<{
        id: z.ZodString;
        kind: z.ZodEnum<["local", "cloud", "embedded"]>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        kind: "local" | "cloud" | "embedded";
    }, {
        id: string;
        kind: "local" | "cloud" | "embedded";
    }>;
    model: z.ZodOptional<z.ZodNullable<z.ZodObject<{
        id: z.ZodString;
        version: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        id: string;
        version: string;
    }, {
        id: string;
        version: string;
    }>>>;
    costClass: z.ZodEnum<["local_zero_inference_cost", "free_keyless", "free_or_variable", "paid", "unknown"]>;
    availability: z.ZodEnum<["READY", "PARTIAL", "ADAPTER_ONLY", "EXTERNAL", "LOCAL_NO_MODEL", "PLANNED", "BLOCKED", "UNKNOWN"]>;
}, "strip", z.ZodTypeAny, {
    capability: "generate_text" | "generate_image" | "edit_image" | "generate_video" | "image_to_video" | "generate_voice" | "generate_music" | "transcribe" | "remove_background" | "upscale" | "analyze_media" | "edit_video" | "compose_video" | "render_video";
    provider: {
        id: string;
        kind: "local" | "cloud" | "embedded";
    };
    costClass: "local_zero_inference_cost" | "free_keyless" | "free_or_variable" | "paid" | "unknown";
    availability: "READY" | "PARTIAL" | "ADAPTER_ONLY" | "EXTERNAL" | "LOCAL_NO_MODEL" | "PLANNED" | "BLOCKED" | "UNKNOWN";
    model?: {
        id: string;
        version: string;
    } | null | undefined;
}, {
    capability: "generate_text" | "generate_image" | "edit_image" | "generate_video" | "image_to_video" | "generate_voice" | "generate_music" | "transcribe" | "remove_background" | "upscale" | "analyze_media" | "edit_video" | "compose_video" | "render_video";
    provider: {
        id: string;
        kind: "local" | "cloud" | "embedded";
    };
    costClass: "local_zero_inference_cost" | "free_keyless" | "free_or_variable" | "paid" | "unknown";
    availability: "READY" | "PARTIAL" | "ADAPTER_ONLY" | "EXTERNAL" | "LOCAL_NO_MODEL" | "PLANNED" | "BLOCKED" | "UNKNOWN";
    model?: {
        id: string;
        version: string;
    } | null | undefined;
}>;
export type CapabilityDescriptor = z.infer<typeof capabilityDescriptorSchema>;
export interface ProviderIdentity {
    readonly id: string;
    readonly kind: "local" | "cloud" | "embedded";
}
export type CurrentnessState = "CURRENT" | "STALE" | "INVALID" | "UNKNOWN";
export type HealthState = "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN";
export type QualificationState = "QUALIFIED" | "UNQUALIFIED" | "UNKNOWN";
export type LicenceState = "ALLOWED" | "DENIED" | "UNKNOWN";
export type HardwareFit = "FIT" | "MISS" | "UNKNOWN";
export interface CapabilityCandidate {
    capability: CapabilityName;
    costClass: CostClass;
    availability: CapabilityAvailability;
    currentness: CurrentnessState;
    health: HealthState;
    qualification: QualificationState;
    licence: LicenceState;
    hardware: HardwareFit;
    evidenceComplete: boolean;
}
export declare const CAPABILITY_REJECTION_REASONS: readonly ["capability_unavailable", "unknown_cost", "disallowed_cost", "stale_currentness", "invalid_currentness", "unknown_currentness", "unhealthy", "unknown_health", "unqualified", "unknown_qualification", "licence_denied", "unknown_licence", "hardware_mismatch", "unknown_hardware", "missing_evidence"];
export type CapabilityRejectionReason = (typeof CAPABILITY_REJECTION_REASONS)[number];
export type CapabilityAdmission = {
    eligible: true;
} | {
    eligible: false;
    reason: CapabilityRejectionReason;
};
export interface CapabilityAdmissionOptions {
    readonly allowedCostClasses?: readonly CostClass[];
}
export declare const DEFAULT_ALLOWED_COST_CLASSES: readonly ["local_zero_inference_cost", "free_keyless"];
export declare function evaluateCapabilityCandidate(candidate: CapabilityCandidate, options?: CapabilityAdmissionOptions): CapabilityAdmission;
