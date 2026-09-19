"""R2 compositing and transition primitives for the existing motion graph."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

BlendMode = Literal["normal","screen","add","multiply","overlay","soft_light"]
MaskKind = Literal["none","rectangle","ellipse","alpha","luma"]

@dataclass(frozen=True)
class MaskSpec:
    kind: MaskKind = "none"
    feather_px: float = 0.0
    invert: bool = False

    def validate(self) -> tuple[str, ...]:
        e=[]
        if self.feather_px < 0: e.append("mask feather_px must be >= 0")
        return tuple(e)

    def to_props(self):
        return {"kind":self.kind,"feather_px":self.feather_px,"invert":self.invert}

@dataclass(frozen=True)
class CompositeSpec:
    blend_mode: BlendMode = "normal"
    opacity: float = 1.0
    blur_px: float = 0.0
    glow: float = 0.0
    mask: MaskSpec = field(default_factory=MaskSpec)
    color_mix: float = 0.0

    def validate(self) -> tuple[str, ...]:
        e=[]
        if not 0 <= self.opacity <= 1: e.append("opacity must be in [0,1]")
        if self.blur_px < 0: e.append("blur_px must be >= 0")
        if self.glow < 0: e.append("glow must be >= 0")
        if not 0 <= self.color_mix <= 1: e.append("color_mix must be in [0,1]")
        return tuple(e)+self.mask.validate()

    def to_props(self):
        return {"blend_mode":self.blend_mode,"opacity":self.opacity,"blur_px":self.blur_px,"glow":self.glow,"mask":self.mask.to_props(),"color_mix":self.color_mix}
