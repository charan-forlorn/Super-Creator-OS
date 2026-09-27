from __future__ import annotations
import re,subprocess
from pathlib import Path
from scos.media_binaries import resolve_ffmpeg
from .contracts import SilenceSpan
_START=re.compile(r"silence_start:\s*([0-9.]+)")
_END=re.compile(r"silence_end:\s*([0-9.]+)")
def detect_silence(path: str|Path,threshold_db: float=-45.0,min_duration: float=0.5)->list[SilenceSpan]:
    cmd=[resolve_ffmpeg(),"-hide_banner","-i",str(Path(path).resolve()),"-af",f"silencedetect=noise={threshold_db}dB:d={min_duration}","-f","null","NUL"]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180,check=False)
    text=(p.stdout or "")+"\n"+(p.stderr or ""); starts=[float(x) for x in _START.findall(text)]; ends=[float(x) for x in _END.findall(text)]
    spans=[]; pending=None
    for value in sorted([(x,"s") for x in starts]+[(x,"e") for x in ends],key=lambda z:z[0]):
        if value[1]=="s": pending=value[0]
        elif pending is not None and value[0]>=pending: spans.append(SilenceSpan(pending,value[0],value[0]-pending)); pending=None
    return spans
def complement_ranges(duration: float,silences:list[SilenceSpan],min_keep:float=0.05)->list[tuple[float,float]]:
    ranges=[]; cursor=0.0
    for s in sorted(silences,key=lambda x:x.start):
        if s.start-cursor>=min_keep: ranges.append((round(cursor,6),round(min(s.start,duration),6)))
        cursor=max(cursor,s.end)
    if duration-cursor>=min_keep: ranges.append((round(cursor,6),round(duration,6)))
    return ranges
