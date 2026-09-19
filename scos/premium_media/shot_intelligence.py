"""R7 deterministic storyboard/shot planner using explicit brief constraints."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

ShotPurpose=Literal["hook","problem","demo","proof","payoff","cta","transition"]

@dataclass(frozen=True)
class ShotPlanSpec:
    shot_id:str
    purpose:ShotPurpose
    start_s:float
    end_s:float
    intensity:float
    visual_focus:str

@dataclass(frozen=True)
class StoryboardPlan:
    duration_s:float
    objective:str
    shots:tuple[ShotPlanSpec,...]

    def to_props(self):
        return {"duration_s":self.duration_s,"objective":self.objective,"shots":[s.__dict__ for s in self.shots]}

    def validate(self)->tuple[str,...]:
        e=[]; prev=-1.0
        for s in self.shots:
            if s.start_s<prev or s.end_s<=s.start_s: e.append(f"{s.shot_id} timing invalid")
            if not 0<=s.intensity<=1: e.append(f"{s.shot_id} intensity invalid")
            prev=s.end_s
        if self.shots and self.shots[-1].end_s>self.duration_s+1e-9: e.append("shots exceed duration")
        return tuple(e)


def plan_storyboard(objective: str, duration_s: float, content_type: str = "short_form") -> StoryboardPlan:
    if duration_s <= 0:
        raise ValueError("duration_s must be > 0")
    if duration_s <= 20:
        names = [("hook", .18), ("demo", .52), ("payoff", .20), ("cta", .10)]
    elif content_type in {"ad", "brand_film"}:
        names = [("hook", .12), ("problem", .20), ("demo", .30), ("proof", .22), ("payoff", .10), ("cta", .06)]
    else:
        names = [("hook", .15), ("problem", .20), ("demo", .35), ("proof", .15), ("payoff", .10), ("cta", .05)]
    shots = []
    t = 0.0
    for i, (purpose, fraction) in enumerate(names):
        end = duration_s * sum(part[1] for part in names[: i + 1])
        shots.append(ShotPlanSpec(f"shot-{i + 1:02d}", purpose, t, end, min(1.0, .45 + i * .1), purpose))
        t = end
    return StoryboardPlan(duration_s, objective, tuple(shots))


def storyboard_to_motion_shell(plan: StoryboardPlan, fps: int = 30):
    from .motion import PremiumMotionGraph, PremiumShot
    errors = plan.validate()
    if errors:
        raise ValueError("; ".join(errors))
    return PremiumMotionGraph(tuple(
        PremiumShot(
            shot_id=s.shot_id,
            start_s=s.start_s,
            end_s=s.end_s,
            purpose=s.purpose,
            pacing="fast" if s.intensity >= .75 else "normal",
        )
        for s in plan.shots
    ), fps=fps)
