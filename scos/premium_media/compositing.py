"""R2 deterministic compositing primitives with renderer-ready mask descriptors."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

BlendMode = Literal["normal", "screen", "add", "multiply", "overlay", "soft_light"]
MaskKind = Literal["none", "rectangle", "ellipse", "alpha", "luma"]

@dataclass(frozen=True)
class MaskSpec:
    kind: MaskKind = "none"
    feather_px: float = 0.0
    invert: bool = False
    source_asset_id: str | None = None

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.feather_px < 0: errors.append("mask feather_px must be >= 0")
        if self.kind in {"alpha", "luma"} and not self.source_asset_id:
            errors.append(f"{self.kind} mask requires source_asset_id")
        if self.kind in {"none", "rectangle", "ellipse"} and self.source_asset_id:
            errors.append(f"{self.kind} mask cannot use source_asset_id")
        if self.source_asset_id and (chr(92) in self.source_asset_id or self.source_asset_id.startswith("/") or ":" in self.source_asset_id):
            errors.append("mask source_asset_id must be a renderer-relative asset path")
        return tuple(errors)

    def to_props(self):
        return {
            "kind": self.kind,
            "feather_px": self.feather_px,
            "invert": self.invert,
            "source_asset_id": self.source_asset_id,
        }

@dataclass(frozen=True)
class CompositeSpec:
    blend_mode: BlendMode = "normal"
    opacity: float = 1.0
    blur_px: float = 0.0
    glow: float = 0.0
    mask: MaskSpec = field(default_factory=MaskSpec)
    color_mix: float = 0.0

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not 0 <= self.opacity <= 1: errors.append("opacity must be in [0,1]")
        if self.blur_px < 0: errors.append("blur_px must be >= 0")
        if self.glow < 0: errors.append("glow must be >= 0")
        if not 0 <= self.color_mix <= 1: errors.append("color_mix must be in [0,1]")
        return tuple(errors) + self.mask.validate()

    def to_props(self):
        return {
            "blend_mode": self.blend_mode,
            "opacity": self.opacity,
            "blur_px": self.blur_px,
            "glow": self.glow,
            "mask": self.mask.to_props(),
            "color_mix": self.color_mix,
        }