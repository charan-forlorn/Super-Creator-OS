from __future__ import annotations
import re,subprocess
from pathlib import Path
from scos.media_binaries import resolve_ffmpeg
from .contracts import CadenceStats,MediaSourceProbe
_FRAME_RE=re.compile(r"frame=\s*([0-9]+)")

def _estimate(path: str|Path,probe: MediaSourceProbe,fps_filter:float|None=None)->CadenceStats:
    vf="mpdecimate=hi=64*12:lo=64*5:frac=0.33"
    if fps_filter: vf=f"fps={fps_filter:.6f},"+vf
    cmd=[resolve_ffmpeg(),"-hide_banner","-i",str(Path(path).resolve()),"-vf",vf,"-an","-f","null","-"]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=600,check=False)
    nums=[int(x) for x in _FRAME_RE.findall((p.stdout or "")+"\n"+(p.stderr or ""))]
    effective_fps=fps_filter or probe.fps
    expected=round(probe.duration_s*effective_fps) if effective_fps>0 else probe.frames
    distinct=nums[-1] if nums else expected
    ratio=max(0.0,min(1.0,1.0-(distinct/max(1,expected))))
    return CadenceStats(effective_fps,expected,distinct,ratio,probe.cfr,True)

def estimate_cadence(path: str|Path,probe: MediaSourceProbe)->CadenceStats:
    return _estimate(path,probe)

def estimate_cadence_normalized(path: str|Path,probe: MediaSourceProbe,target_fps:float)->CadenceStats:
    return _estimate(path,probe,target_fps)
