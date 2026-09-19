"""R8 repeatable capability benchmark harness built on existing contracts."""
from __future__ import annotations
from dataclasses import dataclass
from .compositing import CompositeSpec
from .lookdev import LookProfile
from .scene3d import ProductScene
from .shot_intelligence import plan_storyboard
from .typography import TypographyPlan

@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    content_type: str
    duration_s: float
    objective: str

@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    passed: bool
    capabilities: tuple[str, ...]
    errors: tuple[str, ...] = ()

def benchmark_case(case: BenchmarkCase) -> BenchmarkResult:
    errors: list[str] = []
    capabilities: list[str] = []
    try:
        plan = plan_storyboard(case.objective, case.duration_s, case.content_type)
        errors.extend(plan.validate()); capabilities.append("storyboard")
        errors.extend(CompositeSpec().validate()); capabilities.append("compositing")
        errors.extend(TypographyPlan().validate()); capabilities.append("typography")
        errors.extend(LookProfile("benchmark").validate()); capabilities.append("lookdev")
        errors.extend(ProductScene("benchmark").validate()); capabilities.append("scene3d")
    except Exception as exc:
        errors.append(str(exc))
    return BenchmarkResult(case.case_id, not errors, tuple(capabilities), tuple(errors))

def benchmark_suite(cases: tuple[BenchmarkCase, ...]) -> tuple[BenchmarkResult, ...]:
    return tuple(benchmark_case(case) for case in cases)
