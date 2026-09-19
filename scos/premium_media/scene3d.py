"""R6 bounded 2.5D/3D product-scene contract for Remotion/WebGL backends."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DepthLayer:
    layer_id:str
    z:float
    parallax:float=1.0
    scale:float=1.0

@dataclass(frozen=True)
class Camera3D:
    x:float=0.0; y:float=0.0; z:float=1000.0
    pitch:float=0.0; yaw:float=0.0; roll:float=0.0
    fov_deg:float=45.0

    def validate(self)->tuple[str,...]:
        e=[]
        if self.z<=0: e.append("camera z must be > 0")
        if not 10<=self.fov_deg<=120: e.append("camera fov out of range")
        return tuple(e)

@dataclass(frozen=True)
class ProductScene:
    scene_id:str
    backend:str="webgl"
    camera:Camera3D=field(default_factory=Camera3D)
    layers:tuple[DepthLayer,...]=()
    lighting_preset:str="studio_soft"

    def validate(self)->tuple[str,...]:
        e=list(self.camera.validate()); ids=set()
        for l in self.layers:
            if l.layer_id in ids: e.append(f"duplicate depth layer {l.layer_id}")
            if l.scale<=0: e.append(f"layer {l.layer_id} scale must be > 0")
            ids.add(l.layer_id)
        return tuple(e)

    def to_props(self):
        return {"scene_id":self.scene_id,"backend":self.backend,"camera":self.camera.__dict__,"layers":[l.__dict__ for l in self.layers],"lighting_preset":self.lighting_preset}
