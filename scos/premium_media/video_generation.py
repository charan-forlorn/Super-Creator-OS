"""AI video director and provider-routing contracts.

This module models the production-layer patterns exposed by leading AI video
platforms without coupling SCOS to a single vendor API. Generation remains an
external capability; SCOS owns the deterministic brief -> shot -> reference ->
provider -> render handoff.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Literal

GenerationMode = Literal[
    "text_to_video",
    "image_to_video",
    "video_to_video",
    "first_last_frame",
    "extend",
    "modify",
]

Capability = Literal[
    "text_to_video",
    "image_to_video",
    "video_to_video",
    "first_last_frame",
    "extend",
    "modify",
    "character_reference",
    "style_reference",
    "camera_control",
    "motion_control",
    "multi_shot",
    "native_audio",
    "audio_visual_sync",
    "4k",
    "hdr",
]

ReferenceKind = Literal[
    "scene",
    "character",
    "object",
    "style",
    "motion",
    "first_frame",
    "last_frame",
    "audio",
    "video",
]

ProviderStatus = Literal["available", "configured", "unconfigured", "unavailable"]

@dataclass(frozen=True)
class ReferenceAsset:
    reference_id: str
    kind: ReferenceKind
    uri: str
    sha256: str
    continuity_key: str = ""

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.reference_id.strip():
            errors.append("reference_id is required")
        if not self.uri.strip():
            errors.append(f"{self.reference_id}: uri is required")
        if len(self.sha256) != 64:
            errors.append(f"{self.reference_id}: sha256 must be 64 hex chars")
        elif any(c not in "0123456789abcdef" for c in self.sha256.lower()):
            errors.append(f"{self.reference_id}: sha256 must be hexadecimal")
        return tuple(errors)

    def to_props(self) -> dict:
        return self.__dict__.copy()

@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    model_id: str
    display_name: str
    capabilities: frozenset[Capability]
    status: ProviderStatus = "available"
    api_env_var: str | None = None
    strengths: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def supports(self, required: set[Capability]) -> bool:
        return required.issubset(self.capabilities)

    def to_props(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": sorted(self.capabilities),
            "status": self.status,
            "api_env_var": self.api_env_var,
            "strengths": list(self.strengths),
            "limitations": list(self.limitations),
        }

@dataclass(frozen=True)
class ShotGenerationSpec:
    shot_id: str
    purpose: str
    mode: GenerationMode
    start_s: float
    end_s: float
    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "9:16"
    references: tuple[ReferenceAsset, ...] = ()
    required_capabilities: frozenset[Capability] = frozenset()
    continuity_keys: tuple[str, ...] = ()
    native_audio: bool = False
    camera_language: str = ""
    motion_language: str = ""
    style_language: str = ""

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.end_s <= self.start_s:
            errors.append(f"{self.shot_id}: end_s must be > start_s")
        if not self.prompt.strip():
            errors.append(f"{self.shot_id}: prompt is required")
        if self.aspect_ratio not in {"9:16", "16:9", "1:1", "4:5", "4:3"}:
            errors.append(f"{self.shot_id}: unsupported aspect_ratio {self.aspect_ratio}")
        if self.native_audio and "native_audio" not in self.required_capabilities:
            errors.append(f"{self.shot_id}: native_audio requires native_audio capability")
        for ref in self.references:
            errors.extend(f"{self.shot_id}: {e}" for e in ref.validate())
        return tuple(errors)

    def to_props(self) -> dict:
        return {
            **self.__dict__,
            "required_capabilities": sorted(self.required_capabilities),
            "references": [r.to_props() for r in self.references],
        }

GenerationTaskState = Literal["queued", "submitted", "running", "succeeded", "failed", "cancelled"]

@dataclass(frozen=True)
class GenerationArtifact:
    uri: str
    sha256: str
    media_type: str = "video/mp4"
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.uri.strip():
            errors.append("artifact uri is required")
        if len(self.sha256) != 64:
            errors.append("artifact sha256 must be 64 hex chars")
        elif any(c not in "0123456789abcdef" for c in self.sha256.lower()):
            errors.append("artifact sha256 must be hexadecimal")
        if self.width is not None and self.width <= 0:
            errors.append("artifact width must be > 0")
        if self.height is not None and self.height <= 0:
            errors.append("artifact height must be > 0")
        if self.duration_s is not None and self.duration_s <= 0:
            errors.append("artifact duration_s must be > 0")
        return tuple(errors)

@dataclass(frozen=True)
class GenerationTask:
    task_id: str
    shot_id: str
    provider_id: str
    model_id: str
    state: GenerationTaskState = "queued"
    attempt: int = 0
    provider_task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    artifact: GenerationArtifact | None = None

    def transition(self, target: GenerationTaskState, *,
                   provider_task_id: str | None = None,
                   error_code: str | None = None,
                   error_message: str | None = None,
                   artifact: GenerationArtifact | None = None) -> "GenerationTask":
        allowed = {
            "queued": {"submitted", "cancelled"},
            "submitted": {"running", "failed", "cancelled"},
            "running": {"succeeded", "failed", "cancelled"},
            "succeeded": set(),
            "failed": {"queued", "cancelled"},
            "cancelled": {"queued"},
        }
        if target not in allowed[self.state]:
            raise ValueError(f"invalid generation task transition {self.state} -> {target}")
        next_attempt = self.attempt + 1 if target == "queued" and self.state == "failed" else self.attempt
        if target == "succeeded" and artifact is None:
            raise ValueError("succeeded generation task requires artifact")
        if target == "failed" and not (error_code or error_message):
            raise ValueError("failed generation task requires error metadata")
        return replace(
            self,
            state=target,
            attempt=next_attempt,
            provider_task_id=provider_task_id or self.provider_task_id,
            error_code=error_code,
            error_message=error_message,
            artifact=artifact,
        )

    def to_props(self) -> dict:
        return {
            **self.__dict__,
            "artifact": self.artifact.__dict__ if self.artifact else None,
        }

@dataclass(frozen=True)
class ProviderDecision:
    shot_id: str
    selected_provider_id: str
    selected_model_id: str
    fallback_provider_ids: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]

    def to_props(self) -> dict:
        return self.__dict__.copy()

@dataclass(frozen=True)
class GenerationPlan:
    project_id: str
    objective: str
    shots: tuple[ShotGenerationSpec, ...]
    decisions: tuple[ProviderDecision, ...]
    director_prompt_version: str = "SCOS_AI_VIDEO_DIRECTOR_R1"

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        seen: set[str] = set()
        previous_end = -1.0
        for shot in self.shots:
            errors.extend(shot.validate())
            if shot.shot_id in seen:
                errors.append(f"duplicate shot_id {shot.shot_id}")
            if shot.start_s < previous_end - 1e-9:
                errors.append(f"shot overlap: {shot.shot_id}")
            seen.add(shot.shot_id)
            previous_end = max(previous_end, shot.end_s)
        decision_ids = {d.shot_id for d in self.decisions}
        if decision_ids != seen:
            errors.append("generation decisions do not cover exactly all shots")
        return tuple(errors)

    def fingerprint(self) -> str:
        errors = self.validate()
        if errors:
            raise ValueError("; ".join(errors))
        raw = json.dumps(
            {
                "project_id": self.project_id,
                "objective": self.objective,
                "shots": [s.to_props() for s in self.shots],
                "decisions": [d.to_props() for d in self.decisions],
                "director_prompt_version": self.director_prompt_version,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_props(self) -> dict:
        return {
            "project_id": self.project_id,
            "objective": self.objective,
            "director_prompt_version": self.director_prompt_version,
            "fingerprint": self.fingerprint(),
            "shots": [s.to_props() for s in self.shots],
            "decisions": [d.to_props() for d in self.decisions],
        }

class ProviderRegistry:
    def __init__(self, profiles: tuple[ProviderProfile, ...]):
        self._profiles = {p.provider_id: p for p in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("provider_id values must be unique")

    def profiles(self) -> tuple[ProviderProfile, ...]:
        return tuple(self._profiles[k] for k in sorted(self._profiles))

    def get(self, provider_id: str) -> ProviderProfile:
        try:
            return self._profiles[provider_id]
        except KeyError as exc:
            raise KeyError(f"unknown provider_id: {provider_id}") from exc

    def route(self, shot: ShotGenerationSpec) -> ProviderDecision:
        required = set(shot.required_capabilities)
        ranked: list[tuple[float, ProviderProfile, tuple[str, ...]]] = []
        for profile in self._profiles.values():
            if profile.status == "unavailable":
                continue
            reasons: list[str] = []
            missing = required - set(profile.capabilities)
            if missing:
                continue
            score = 0.0
            if shot.native_audio and "native_audio" in profile.capabilities:
                score += 30.0; reasons.append("native-audio")
            if shot.camera_language and "camera_control" in profile.capabilities:
                score += 15.0; reasons.append("camera-control")
            if shot.motion_language and "motion_control" in profile.capabilities:
                score += 15.0; reasons.append("motion-control")
            if any(r.kind == "character" for r in shot.references):
                if "character_reference" in profile.capabilities:
                    score += 20.0; reasons.append("character-reference")
            if any(r.kind == "style" for r in shot.references):
                if "style_reference" in profile.capabilities:
                    score += 10.0; reasons.append("style-reference")
            if any(r.kind == "first_frame" for r in shot.references) or any(r.kind == "last_frame" for r in shot.references):
                if "first_last_frame" in profile.capabilities:
                    score += 20.0; reasons.append("frame-control")
            if shot.mode in {"video_to_video", "modify"} and "video_to_video" in profile.capabilities:
                score += 20.0; reasons.append("video-editing")
            if shot.mode == "extend" and "extend" in profile.capabilities:
                score += 18.0; reasons.append("extension")
            if profile.status == "configured":
                score += 5.0; reasons.append("configured")
            ranked.append((score, profile, tuple(reasons)))
        if not ranked:
            raise LookupError(
                f"no configured/available provider satisfies capabilities for {shot.shot_id}: "
                f"{sorted(required)}"
            )
        ranked.sort(key=lambda x: (-x[0], x[1].provider_id))
        selected = ranked[0]
        fallbacks = tuple(item[1].provider_id for item in ranked[1:])
        return ProviderDecision(
            shot_id=shot.shot_id,
            selected_provider_id=selected[1].provider_id,
            selected_model_id=selected[1].model_id,
            fallback_provider_ids=fallbacks,
            score=selected[0],
            reasons=selected[2],
        )

    def plan(self, project_id: str, objective: str, shots: tuple[ShotGenerationSpec, ...]) -> GenerationPlan:
        decisions = tuple(self.route(shot) for shot in shots)
        plan = GenerationPlan(project_id, objective, shots, decisions)
        errors = plan.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return plan

def compile_director_prompt(
    objective: str,
    shot: ShotGenerationSpec,
    *,
    continuity_summary: str = "",
) -> str:
    """Compile model-facing shot instructions from structured creative intent."""
    parts = [
        f"PROJECT OBJECTIVE: {objective.strip()}",
        f"SHOT PURPOSE: {shot.purpose}",
        f"SHOT WINDOW: {shot.start_s:.3f}s-{shot.end_s:.3f}s",
        f"FORMAT: {shot.aspect_ratio}",
        f"SCENE DIRECTION: {shot.prompt.strip()}",
    ]
    if shot.camera_language:
        parts.append(f"CAMERA: {shot.camera_language.strip()}")
    if shot.motion_language:
        parts.append(f"MOTION: {shot.motion_language.strip()}")
    if shot.style_language:
        parts.append(f"STYLE: {shot.style_language.strip()}")
    if continuity_summary:
        parts.append(f"CONTINUITY: {continuity_summary.strip()}")
    if shot.negative_prompt:
        parts.append(f"AVOID: {shot.negative_prompt.strip()}")
    parts.append(
        "DELIVERY: maintain stable subject identity, coherent spatial layout, "
        "consistent lighting direction, deliberate cinematic pacing, and a clean "
        "edit-ready composition."
    )
    return "\n".join(parts)

def build_generation_plan(
    project_id: str,
    objective: str,
    storyboard,
    *,
    registry: ProviderRegistry,
    aspect_ratio: str = "9:16",
    native_audio: bool = True,
    global_references: tuple[ReferenceAsset, ...] = (),
) -> GenerationPlan:
    """Compile a storyboard into provider-routable shot generation specs."""
    shots: list[ShotGenerationSpec] = []
    for shot in storyboard.shots:
        refs = tuple(global_references)
        required: set[Capability] = {"camera_control"}
        if native_audio:
            required.update({"native_audio", "audio_visual_sync"})
        if any(ref.kind == "character" for ref in refs):
            required.add("character_reference")
        if any(ref.kind == "style" for ref in refs):
            required.add("style_reference")
        mode: GenerationMode = "text_to_video"
        shots.append(
            ShotGenerationSpec(
                shot_id=shot.shot_id,
                purpose=shot.purpose,
                mode=mode,
                start_s=shot.start_s,
                end_s=shot.end_s,
                prompt=(
                    f"Create a premium {shot.purpose} shot for: {objective}. "
                    f"Visual focus: {shot.visual_focus}. "
                    "Use deliberate framing, physical continuity, and edit-ready motion."
                ),
                aspect_ratio=aspect_ratio,
                references=refs,
                required_capabilities=frozenset(required),
                continuity_keys=tuple(sorted({ref.continuity_key for ref in refs if ref.continuity_key})),
                native_audio=native_audio,
                camera_language="cinematic controlled camera movement",
                motion_language="physically coherent subject motion with restrained secondary motion",
            )
        )
    return registry.plan(project_id, objective, tuple(shots))

def generation_plan_from_props(props: dict) -> GenerationPlan:
    shots: list[ShotGenerationSpec] = []
    for raw in props.get("shots", ()):
        refs = tuple(
            ReferenceAsset(
                reference_id=str(r["reference_id"]),
                kind=r["kind"],
                uri=str(r["uri"]),
                sha256=str(r["sha256"]),
                continuity_key=str(r.get("continuity_key", "")),
            )
            for r in raw.get("references", ())
        )
        shots.append(
            ShotGenerationSpec(
                shot_id=str(raw["shot_id"]),
                purpose=str(raw["purpose"]),
                mode=raw["mode"],
                start_s=float(raw["start_s"]),
                end_s=float(raw["end_s"]),
                prompt=str(raw["prompt"]),
                negative_prompt=str(raw.get("negative_prompt", "")),
                aspect_ratio=str(raw.get("aspect_ratio", "9:16")),
                references=refs,
                required_capabilities=frozenset(raw.get("required_capabilities", ())),
                continuity_keys=tuple(raw.get("continuity_keys", ())),
                native_audio=bool(raw.get("native_audio", False)),
                camera_language=str(raw.get("camera_language", "")),
                motion_language=str(raw.get("motion_language", "")),
                style_language=str(raw.get("style_language", "")),
            )
        )
    decisions = tuple(
        ProviderDecision(
            shot_id=str(d["shot_id"]),
            selected_provider_id=str(d["selected_provider_id"]),
            selected_model_id=str(d["selected_model_id"]),
            fallback_provider_ids=tuple(d.get("fallback_provider_ids", ())),
            score=float(d["score"]),
            reasons=tuple(d.get("reasons", ())),
        )
        for d in props.get("decisions", ())
    )
    return GenerationPlan(
        project_id=str(props["project_id"]),
        objective=str(props["objective"]),
        shots=tuple(shots),
        decisions=decisions,
        director_prompt_version=str(props.get("director_prompt_version", "SCOS_AI_VIDEO_DIRECTOR_R1")),
    )

DEFAULT_PROVIDER_PROFILES = (
    ProviderProfile(
        "google_veo",
        "veo-3.1",
        "Google Veo 3.1",
        frozenset({"text_to_video","image_to_video","extend","first_last_frame","character_reference","style_reference","camera_control","motion_control","native_audio","audio_visual_sync","4k"}),
        strengths=("realism","physics","native-audio","camera-control","references"),
    ),
    ProviderProfile(
        "bytedance_seedance",
        "seedance-2.0",
        "ByteDance Seedance 2.0",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","modify","first_last_frame","character_reference","style_reference","camera_control","motion_control","multi_shot","native_audio","audio_visual_sync","4k"}),
        strengths=("multimodal-reference","multi-shot","audio-video","complex-motion"),
    ),
    ProviderProfile(
        "runway",
        "gen4.5",
        "Runway Gen-4.5",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","modify","first_last_frame","style_reference","camera_control","motion_control","multi_shot","4k"}),
        strengths=("creative-control","video-workflow","reference-driven-production"),
    ),
    ProviderProfile(
        "kling",
        "kling-3.0",
        "Kling 3.0",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","modify","character_reference","camera_control","motion_control","native_audio","4k","hdr"}),
        strengths=("human-motion","camera-control","longer-form-shot-work"),
    ),
    ProviderProfile(
        "luma",
        "ray3.14",
        "Luma Ray3.14",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","modify","first_last_frame","character_reference","style_reference","camera_control","motion_control","4k","hdr"}),
        strengths=("modify-video","keyframes","character-reference","hdr"),
    ),
    ProviderProfile(
        "adobe_firefly",
        "firefly-video-router",
        "Adobe Firefly Video",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","modify","style_reference","camera_control","4k"}),
        strengths=("multi-model-workflow","creative-suite-integration","delivery"),
    ),
    ProviderProfile(
        "minimax_hailuo",
        "hailuo",
        "MiniMax Hailuo",
        frozenset({"text_to_video","image_to_video","video_to_video","extend","character_reference","motion_control"}),
        strengths=("character-consistency","motion"),
    ),
    ProviderProfile(
        "pika",
        "pika",
        "Pika",
        frozenset({"text_to_video","image_to_video","video_to_video","modify","extend"}),
        strengths=("fast-iteration","social-content"),
    ),
    ProviderProfile(
        "xai_grok",
        "grok-imagine-video",
        "xAI Grok Imagine Video",
        frozenset({"text_to_video","image_to_video"}),
        strengths=("fast-exploration",),
    ),
    ProviderProfile(
        "heygen",
        "video-api",
        "HeyGen Video API",
        frozenset({"text_to_video","image_to_video","multi_shot","native_audio"}),
        strengths=("avatar","presentation","business-video"),
    ),
)
