from __future__ import annotations
import re,subprocess
from pathlib import Path
from scos.media_binaries import resolve_ffmpeg
from .contracts import SceneBoundary
_PTS=re.compile(r"pts_time:([0-9.]+)")
def detect_scene_boundaries(path: str|Path,threshold: float=0.30)->list[SceneBoundary]:
    cmd=[resolve_ffmpeg(),"-hide_banner","-i",str(Path(path).resolve()),"-vf",f"select='gt(scene,{threshold})',showinfo","-an","-f","null","-"]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=300,check=False)
    times=[]
    for value in _PTS.findall((p.stdout or "")+"\n"+(p.stderr or "")):
        t=float(value)
        if not times or abs(t-times[-1])>0.05: times.append(t)
    return [SceneBoundary(t,threshold) for t in times]
