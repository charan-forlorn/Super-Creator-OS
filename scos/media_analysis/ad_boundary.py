from __future__ import annotations
from typing import Sequence
from .contracts import AdBoundary,SceneBoundary,SilenceSpan

def infer_final_ad_boundary(duration: float, scenes: Sequence[SceneBoundary], broad_silences: Sequence[SilenceSpan])->AdBoundary|None:
    late=[s for s in scenes if s.time>=max(0.0,duration-8.0)]
    if not late: return None
    trigger=late[-1].time
    candidates=sorted(
        [s for s in broad_silences if 1.0<=s.duration and s.start>=5.0 and s.start<trigger and s.end<=trigger+0.5],
        key=lambda s:s.start,
    )
    if not candidates: return None
    chosen=candidates[0]
    if trigger-chosen.start<1.0: return None
    confidence=min(0.99,0.70+0.05*min(len(late),4)+0.10*min(chosen.duration/2.0,1.0))
    return AdBoundary(round(chosen.start,6),round(trigger,6),round(confidence,3),
                      "late scene boundary follows a sustained broad silence; earliest post-intro sustained silence selected as content end")
