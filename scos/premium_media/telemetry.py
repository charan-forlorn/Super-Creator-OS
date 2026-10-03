
"""Observable generation telemetry and provider A/B evaluation primitives."""
from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class GenerationTelemetryEvent:
    schema_version: str
    observed_at: float
    task_id: str
    shot_id: str
    provider_id: str
    model_id: str
    attempt: int
    state: str
    latency_s: float | None = None
    cost_units: float | None = None
    quality_score: float | None = None
    qc_passed: bool | None = None
    metadata: dict | None = None

    def to_json(self) -> dict:
        return dict(self.__dict__)


class JsonlTelemetrySink:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: GenerationTelemetryEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_json(), ensure_ascii=False, sort_keys=True) + "\n")


def utility_score(*, quality_score: float, latency_s: float | None, cost_units: float | None, quality_weight: float = 0.70, latency_weight: float = 0.15, cost_weight: float = 0.15) -> float:
    quality = max(0.0, min(1.0, quality_score))
    latency_penalty = 0.0 if latency_s is None else min(1.0, latency_s / 300.0)
    cost_penalty = 0.0 if cost_units is None else min(1.0, cost_units / 100.0)
    return quality_weight * quality - latency_weight * latency_penalty - cost_weight * cost_penalty


@dataclass(frozen=True)
class ProviderEvaluationCandidate:
    shot_id: str
    provider_id: str
    model_id: str
    quality_score: float
    latency_s: float | None = None
    cost_units: float | None = None
    qc_passed: bool = True

    @property
    def utility(self) -> float:
        return utility_score(quality_score=self.quality_score, latency_s=self.latency_s, cost_units=self.cost_units)


@dataclass(frozen=True)
class ProviderEvaluation:
    shot_id: str
    selected_provider_id: str
    selected_model_id: str
    selected_utility: float
    candidates: tuple[ProviderEvaluationCandidate, ...]


def evaluate_provider_candidates(candidates: Iterable[ProviderEvaluationCandidate]) -> ProviderEvaluation:
    items = tuple(c for c in candidates if c.qc_passed)
    if not items:
        raise ValueError("no QC-passed provider candidates")
    best = max(items, key=lambda c: (c.utility, c.quality_score, -(c.latency_s or math.inf)))
    return ProviderEvaluation(items[0].shot_id, best.provider_id, best.model_id, best.utility, items)


def observed_latency(started_at: float | None, completed_at: float | None) -> float | None:
    if started_at is None or completed_at is None:
        return None
    return max(0.0, completed_at - started_at)


def now() -> float:
    return time.time()
