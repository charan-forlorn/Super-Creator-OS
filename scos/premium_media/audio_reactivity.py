"""R3 audio-reactive analysis from real decoded audio bytes only."""
from __future__ import annotations
import math, struct, subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class EnergyEvent:
    time_s: float
    strength: float

@dataclass(frozen=True)
class AudioReactiveAnalysis:
    duration_s: float
    sample_rate: int
    window_s: float
    rms: tuple[float,...]
    events: tuple[EnergyEvent,...]

    def to_props(self):
        return {"duration_s":self.duration_s,"sample_rate":self.sample_rate,"window_s":self.window_s,"events":[e.__dict__ for e in self.events]}

def _decode_mono_pcm(path: str|Path, sample_rate:int=8000)->bytes:
    p=Path(path).resolve()
    proc=subprocess.run(["ffmpeg","-v","error","-i",str(p),"-ac","1","-ar",str(sample_rate),"-f","s16le","-"],capture_output=True,timeout=180)
    if proc.returncode: raise RuntimeError((proc.stderr or b"decode failed")[-2000:].decode(errors="replace"))
    if not proc.stdout: raise ValueError("audio decode produced no PCM bytes")
    return proc.stdout

def analyze_audio(path:str|Path, sample_rate:int=8000, window_s:float=0.20)->AudioReactiveAnalysis:
    raw=_decode_mono_pcm(path,sample_rate); step=max(1,int(sample_rate*window_s)); vals=[]
    for i in range(0,len(raw)-1,step*2):
        block=raw[i:i+step*2]; n=len(block)//2
        if not n: continue
        samples=struct.unpack("<"+"h"*n,block[:n*2]); vals.append(math.sqrt(sum(x*x for x in samples)/(n*32768.0)**2))
    baseline=sorted(vals)[len(vals)//2] if vals else 0.0
    floor=max(min(vals) if vals else 0.0, 0.002)
    threshold=max(floor*1.8, baseline*1.25, 0.008)
    events=tuple(EnergyEvent(i*window_s,min(1.0,v/max(threshold,1e-6))) for i,v in enumerate(vals) if v>threshold)
    return AudioReactiveAnalysis(len(raw)/2/sample_rate,sample_rate,window_s,tuple(vals),events)
