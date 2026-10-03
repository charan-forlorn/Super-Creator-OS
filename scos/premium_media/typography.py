"""R4 kinetic typography and word-level caption grammar."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

TypographyPreset = Literal["clean","kinetic","emphasis","speaker","product"]

@dataclass(frozen=True)
class WordCue:
    text:str
    start_s:float
    end_s:float
    emphasis:float=0.0

@dataclass(frozen=True)
class TypographyStyle:
    preset:TypographyPreset="clean"
    font_family:str="Inter"
    size_px:int=56
    weight:int=700
    color:str="#FFFFFF"
    accent_color:str="#7BE0C3"
    tracking_px:float=0.0
    max_lines:int=2

    def validate(self)->tuple[str,...]:
        e=[]
        if self.size_px<=0: e.append("font size must be > 0")
        if not 100<=self.weight<=1000: e.append("font weight out of range")
        if self.max_lines<1: e.append("max_lines must be >= 1")
        return tuple(e)

@dataclass(frozen=True)
class TypographyPlan:
    style:TypographyStyle=TypographyStyle()
    words:tuple[WordCue,...]=()

    def validate(self)->tuple[str,...]:
        e=list(self.style.validate()); prev=-1.0
        for i,w in enumerate(self.words):
            if w.start_s<prev or w.end_s<=w.start_s: e.append(f"word {i} timing invalid")
            if not 0<=w.emphasis<=1: e.append(f"word {i} emphasis out of range")
            prev=w.end_s
        return tuple(e)

    def to_props(self):
        return {"style":self.style.__dict__,"words":[w.__dict__ for w in self.words]}
