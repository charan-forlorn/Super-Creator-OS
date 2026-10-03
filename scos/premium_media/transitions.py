"""R2 transition utilities; reuses the canonical R1 ShotTransition contract."""
from __future__ import annotations
from .motion import ShotTransition

TransitionRuntimeSpec = ShotTransition

def compile_transition_filter(spec: TransitionRuntimeSpec) -> str:
    errors = spec.validate("transition")
    if errors:
        raise ValueError("; ".join(errors))
    if spec.type == "cut":
        return "cut"
    return f"{spec.type}:{spec.direction}:{spec.duration_s:.3f}"
