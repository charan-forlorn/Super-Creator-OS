"""Carries per-run state and the execution trace through the Stage 1 pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineState:
    input_prompt: str
    execution_trace: list = field(default_factory=list)
    script: dict | None = None
    scene_plan: dict | None = None
    asset_bundle: dict | None = None
    edit_timeline: dict | None = None
    video_path: str | None = None
    qa_report: dict | None = None

    def record(self, stage: str, status: str, error: str | None = None) -> None:
        entry = {"stage": stage, "status": status}
        if error is not None:
            entry["error"] = error
        self.execution_trace.append(entry)
