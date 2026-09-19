"""Deterministic premium shot/motion grammar for Remotion and render backends.

This module is render-engine agnostic. It turns premium editorial primitives
(shots, layers, keyframes, transitions, camera, effects) into a validated,
fingerprintable contract that the existing ProductionGraph can carry into
Remotion props without creating a parallel orchestration subsystem.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

EasingName = Literal["linear", "ease_in", "ease_out", "ease_in_out", "sharp"]
TransitionName = Literal["cut", "crossfade", "dip_to_black", "dip_to_white", "slide", "zoom", "whip"]
LayerKind = Literal["media", "text", "shape", "particle", "caption", "overlay"]


@dataclass(frozen=True)
class Keyframe:
    time_s: float
    value: float
    easing: EasingName = "linear"


@dataclass(frozen=True)
class AnimatedNumber:
    value: float = 0.0
    keyframes: tuple[Keyframe, ...] = ()

    def validate(self, field_name: str) -> tuple[str, ...]:
        errors: list[str] = []
        if self.keyframes and abs(self.keyframes[0].time_s) > 1e-9:
            errors.append(f"{field_name}: first keyframe must start at 0s")
        previous = -1.0
        for index, keyframe in enumerate(self.keyframes):
            if keyframe.time_s < 0:
                errors.append(f"{field_name}: keyframe {index} has negative time")
            if keyframe.time_s <= previous:
                errors.append(f"{field_name}: keyframe times must be strictly increasing")
            if not isinstance(keyframe.value, (int, float)):
                errors.append(f"{field_name}: keyframe {index} value must be numeric")
            previous = keyframe.time_s
        return tuple(errors)

    def to_props(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "keyframes": [
                {"time_s": k.time_s, "value": k.value, "easing": k.easing}
                for k in self.keyframes
            ],
        }


@dataclass(frozen=True)
class Transform2D:
    x: AnimatedNumber = field(default_factory=AnimatedNumber)
    y: AnimatedNumber = field(default_factory=AnimatedNumber)
    scale: AnimatedNumber = field(default_factory=lambda: AnimatedNumber(1.0))
    rotation_deg: AnimatedNumber = field(default_factory=AnimatedNumber)
    opacity: AnimatedNumber = field(default_factory=lambda: AnimatedNumber(1.0))

    def validate(self) -> tuple[str, ...]:
        fields = ("x", self.x), ("y", self.y), ("scale", self.scale), ("rotation_deg", self.rotation_deg), ("opacity", self.opacity)
        errors = [err for name, value in fields for err in value.validate(f"transform.{name}")]
        if self.scale.value <= 0:
            errors.append("transform.scale must be > 0")
        if not 0 <= self.opacity.value <= 1:
            errors.append("transform.opacity must be in [0,1]")
        return tuple(errors)

    def to_props(self) -> dict[str, Any]:
        return {
            "x": self.x.to_props(), "y": self.y.to_props(),
            "scale": self.scale.to_props(), "rotation_deg": self.rotation_deg.to_props(),
            "opacity": self.opacity.to_props(),
        }


@dataclass(frozen=True)
class Camera2D:
    x: AnimatedNumber = field(default_factory=AnimatedNumber)
    y: AnimatedNumber = field(default_factory=AnimatedNumber)
    zoom: AnimatedNumber = field(default_factory=lambda: AnimatedNumber(1.0))
    rotation_deg: AnimatedNumber = field(default_factory=AnimatedNumber)
    depth: float = 0.0

    def validate(self) -> tuple[str, ...]:
        fields = ("x", self.x), ("y", self.y), ("zoom", self.zoom), ("rotation_deg", self.rotation_deg)
        return tuple(err for name, value in fields for err in value.validate(f"camera.{name}")) + (() if self.zoom.value > 0 else ("camera.zoom must be > 0",))

    def to_props(self) -> dict[str, Any]:
        return {
            "x": self.x.to_props(), "y": self.y.to_props(),
            "zoom": self.zoom.to_props(), "rotation_deg": self.rotation_deg.to_props(),
            "depth": self.depth,
        }


@dataclass(frozen=True)
class EffectStack:
    blur_px: AnimatedNumber = field(default_factory=AnimatedNumber)
    brightness: AnimatedNumber = field(default_factory=AnimatedNumber)
    contrast: AnimatedNumber = field(default_factory=lambda: AnimatedNumber(1.0))
    saturation: AnimatedNumber = field(default_factory=lambda: AnimatedNumber(1.0))
    glow: AnimatedNumber = field(default_factory=AnimatedNumber)
    vignette: AnimatedNumber = field(default_factory=AnimatedNumber)
    grain: AnimatedNumber = field(default_factory=AnimatedNumber)

    def validate(self) -> tuple[str, ...]:
        fields = ("blur_px", self.blur_px), ("brightness", self.brightness), ("contrast", self.contrast), ("saturation", self.saturation), ("glow", self.glow), ("vignette", self.vignette), ("grain", self.grain)
        errors = [err for name, value in fields for err in value.validate(f"effects.{name}")]
        if self.blur_px.value < 0: errors.append("effects.blur_px must be >= 0")
        if self.contrast.value < 0: errors.append("effects.contrast must be >= 0")
        if self.saturation.value < 0: errors.append("effects.saturation must be >= 0")
        return tuple(errors)

    def to_props(self) -> dict[str, Any]:
        return {name: value.to_props() for name, value in (
            ("blur_px", self.blur_px), ("brightness", self.brightness), ("contrast", self.contrast),
            ("saturation", self.saturation), ("glow", self.glow), ("vignette", self.vignette), ("grain", self.grain),
        )}


@dataclass(frozen=True)
class MotionLayer:
    layer_id: str
    kind: LayerKind
    z_index: int
    start_s: float
    end_s: float
    asset_id: str | None = None
    text: str = ""
    transform: Transform2D = field(default_factory=Transform2D)
    effects: EffectStack = field(default_factory=EffectStack)
    blend_mode: str = "normal"
    mask: str | None = None

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.layer_id.strip(): errors.append("layer_id is required")
        if self.end_s <= self.start_s: errors.append(f"{self.layer_id}: end_s must be > start_s")
        if self.kind == "media" and not self.asset_id: errors.append(f"{self.layer_id}: media layer requires asset_id")
        if self.kind == "text" and not self.text.strip(): errors.append(f"{self.layer_id}: text layer requires text")
        errors.extend(self.transform.validate())
        errors.extend(self.effects.validate())
        return tuple(errors)

    def to_props(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id, "kind": self.kind, "z_index": self.z_index,
            "start_s": self.start_s, "end_s": self.end_s, "asset_id": self.asset_id, "text": self.text,
            "transform": self.transform.to_props(), "effects": self.effects.to_props(),
            "blend_mode": self.blend_mode, "mask": self.mask,
        }


@dataclass(frozen=True)
class ShotTransition:
    type: TransitionName = "cut"
    duration_s: float = 0.0
    easing: EasingName = "ease_in_out"
    direction: str = "forward"

    def validate(self, field_name: str) -> tuple[str, ...]:
        if self.type == "cut":
            return () if self.duration_s == 0 else (f"{field_name}: cut duration must be 0",)
        if not 0 < self.duration_s <= 2.0:
            return (f"{field_name}: duration must be within (0,2]",)
        return ()

    def to_props(self) -> dict[str, Any]:
        return {"type": self.type, "duration_s": self.duration_s, "easing": self.easing, "direction": self.direction}


@dataclass(frozen=True)
class PremiumShot:
    shot_id: str
    start_s: float
    end_s: float
    purpose: str = "story"
    pacing: str = "normal"
    camera: Camera2D = field(default_factory=Camera2D)
    layers: tuple[MotionLayer, ...] = ()
    transition_in: ShotTransition = field(default_factory=ShotTransition)
    transition_out: ShotTransition = field(default_factory=ShotTransition)

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.shot_id.strip(): errors.append("shot_id is required")
        if self.end_s <= self.start_s: errors.append(f"{self.shot_id}: end_s must be > start_s")
        errors.extend(self.camera.validate())
        seen: set[str] = set()
        z_seen: set[int] = set()
        for layer in self.layers:
            errors.extend(f"{self.shot_id}: {e}" for e in layer.validate())
            if layer.layer_id in seen: errors.append(f"{self.shot_id}: duplicate layer_id {layer.layer_id}")
            if layer.z_index in z_seen: errors.append(f"{self.shot_id}: duplicate z_index {layer.z_index}")
            seen.add(layer.layer_id); z_seen.add(layer.z_index)
            if layer.start_s < self.start_s or layer.end_s > self.end_s:
                errors.append(f"{self.shot_id}: layer {layer.layer_id} escapes shot bounds")
        errors.extend(self.transition_in.validate(f"{self.shot_id}.transition_in"))
        errors.extend(self.transition_out.validate(f"{self.shot_id}.transition_out"))
        return tuple(errors)

    def to_props(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id, "start_s": self.start_s, "end_s": self.end_s,
            "purpose": self.purpose, "pacing": self.pacing, "camera": self.camera.to_props(),
            "layers": [layer.to_props() for layer in sorted(self.layers, key=lambda x: x.z_index)],
            "transition_in": self.transition_in.to_props(), "transition_out": self.transition_out.to_props(),
        }


@dataclass(frozen=True)
class PremiumMotionGraph:
    shots: tuple[PremiumShot, ...] = ()
    fps: int = 30
    schema_version: str = "SCOS_PREMIUM_MOTION_GRAPH_R1"

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.fps <= 0: errors.append("fps must be > 0")
        ordered = sorted(self.shots, key=lambda x: (x.start_s, x.end_s, x.shot_id))
        previous_end = -1.0
        seen_ids: set[str] = set()
        for shot in ordered:
            errors.extend(shot.validate())
            if shot.shot_id in seen_ids: errors.append(f"duplicate shot_id {shot.shot_id}")
            if shot.start_s < previous_end - 1e-9:
                errors.append(f"shot overlap: {shot.shot_id} starts before {previous_end:.3f}s")
            previous_end = max(previous_end, shot.end_s)
            seen_ids.add(shot.shot_id)
        return tuple(errors)

    def assert_valid(self) -> None:
        errors = self.validate()
        if errors: raise ValueError("; ".join(errors))

    def fingerprint(self) -> str:
        self.assert_valid()
        raw = json.dumps(self.to_props(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_props(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fps": self.fps,
            "fingerprint": None,
            "shots": [shot.to_props() for shot in sorted(self.shots, key=lambda x: (x.start_s, x.end_s, x.shot_id))],
        }


def with_fingerprint(graph: PremiumMotionGraph) -> dict[str, Any]:
    props = graph.to_props()
    props["fingerprint"] = graph.fingerprint()
    return props