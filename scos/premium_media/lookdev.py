"""R5 deterministic look-development contract and FFmpeg filter compilation."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class LookProfile:
    profile_id:str
    exposure:float=0.0
    contrast:float=1.0
    saturation:float=1.0
    gamma:float=1.0
    temperature:float=0.0
    tint:float=0.0
    lut_path:str|None=None

    def validate(self)->tuple[str,...]:
        e=[]
        if self.contrast<0: e.append("contrast must be >= 0")
        if self.saturation<0: e.append("saturation must be >= 0")
        if self.gamma<=0: e.append("gamma must be > 0")
        if self.lut_path and not Path(self.lut_path).is_file(): e.append("lut_path missing")
        return tuple(e)

    def fingerprint(self)->str:
        p=Path(self.lut_path).resolve() if self.lut_path else None
        payload=f"{self.profile_id}|{self.exposure}|{self.contrast}|{self.saturation}|{self.gamma}|{self.temperature}|{self.tint}"
        if p and p.is_file(): payload += "|" + hashlib.sha256(p.read_bytes()).hexdigest()
        return hashlib.sha256(payload.encode()).hexdigest()

    def ffmpeg_filter(self)->str:
        self.validate() or None
        base=f"eq=brightness={self.exposure:.4f}:contrast={self.contrast:.4f}:saturation={self.saturation:.4f}:gamma={self.gamma:.4f}"
        return f"lut3d='{Path(self.lut_path).as_posix()}',{base}" if self.lut_path else base
