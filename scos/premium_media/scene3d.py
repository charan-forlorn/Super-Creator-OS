"""R6 true-3D scene contract for the canonical Remotion WebGL runtime."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

SceneBackend = Literal["three", "2.5d"]
AssetKind = Literal["gltf", "box", "sphere", "plane"]

@dataclass(frozen=True)
class DepthLayer:
    layer_id: str
    z: float
    parallax: float = 1.0
    scale: float = 1.0
    asset_id: str | None = None
    asset_kind: AssetKind = "box"

@dataclass(frozen=True)
class Camera3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 1000.0
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    fov_deg: float = 45.0

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.z <= 0: errors.append("camera z must be > 0")
        if not 10 <= self.fov_deg <= 120: errors.append("camera fov out of range")
        return tuple(errors)

@dataclass(frozen=True)
class ProductScene:
    scene_id: str
    backend: SceneBackend = "three"
    camera: Camera3D = field(default_factory=Camera3D)
    layers: tuple[DepthLayer, ...] = ()
    lighting_preset: str = "studio_soft"

    def validate(self) -> tuple[str, ...]:
        errors = list(self.camera.validate())
        ids: set[str] = set()
        for layer in self.layers:
            if layer.layer_id in ids: errors.append(f"duplicate depth layer {layer.layer_id}")
            if layer.scale <= 0: errors.append(f"layer {layer.layer_id} scale must be > 0")
            if layer.asset_kind == "gltf" and not layer.asset_id:
                errors.append(f"layer {layer.layer_id} gltf layer requires asset_id")
            if layer.asset_id and (chr(92) in layer.asset_id or layer.asset_id.startswith("/") or ":" in layer.asset_id):
                errors.append(f"layer {layer.layer_id} asset_id must be renderer-relative")
            if not -10_000 <= layer.z <= 10_000:
                errors.append(f"layer {layer.layer_id} z out of range")
            ids.add(layer.layer_id)
        if self.backend not in {"three", "2.5d"}:
            errors.append(f"unsupported scene backend {self.backend}")
        return tuple(errors)

    def to_props(self):
        return {
            "scene_id": self.scene_id,
            "backend": self.backend,
            "camera": self.camera.__dict__,
            "layers": [layer.__dict__ for layer in self.layers],
            "lighting_preset": self.lighting_preset,
        }