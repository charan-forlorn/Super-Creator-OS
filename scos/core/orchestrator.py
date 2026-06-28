"""Stage 1 pipeline controller.

Input -> Script -> Scene Plan -> Asset Build -> Edit Plan -> Render -> QA -> Output -> Memory Log
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from scos.agents.asset_builder import AssetBuilder
from scos.agents.edit_composer import EditComposer
from scos.agents.qa_agent import QAAgent
from scos.agents.scene_planner import ScenePlanner
from scos.agents.script_agent import ScriptAgent
from scos.core.pipeline_state import PipelineState
from scos.memory import memory_writer
from scos.render import ffmpeg_engine

STAGES = ["script", "scene_plan", "asset_build", "edit_plan", "render", "qa"]


def _run_id(input_prompt: str) -> str:
    return hashlib.sha256(input_prompt.encode()).hexdigest()[:12]


def run_pipeline(input_prompt: str) -> dict:
    state = PipelineState(input_prompt=input_prompt)
    run_id = _run_id(input_prompt)

    agents = {
        "script": ScriptAgent(),
        "scene_plan": ScenePlanner(),
        "asset_build": AssetBuilder(),
        "edit_plan": EditComposer(),
        "render": ffmpeg_engine,
        "qa": QAAgent(),
    }

    try:
        state.script = agents["script"].run({"input_prompt": input_prompt})
        state.record("script", "success")

        state.scene_plan = agents["scene_plan"].run({"script": state.script})
        state.record("scene_plan", "success")

        state.asset_bundle = agents["asset_build"].run(
            {"run_id": run_id, "scene_plan": state.scene_plan}
        )
        state.record("asset_build", "success")

        state.edit_timeline = agents["edit_plan"].run(
            {"scene_plan": state.scene_plan, "asset_bundle": state.asset_bundle}
        )
        state.record("edit_plan", "success")

        render_result = agents["render"].render(
            {"run_id": run_id, "edit_timeline": state.edit_timeline}
        )
        state.video_path = render_result["video_path"]
        state.record("render", "success")

        state.qa_report = agents["qa"].run({"edit_timeline": state.edit_timeline})
        state.record("qa", "success")

        status = "success"

    except Exception as exc:  # noqa: BLE001 - top-level pipeline error boundary
        failed_stage = STAGES[len(state.execution_trace)]
        state.record(failed_stage, "failed", error=str(exc))
        status = "failed"

    result = {
        "status": status,
        "input_prompt": input_prompt,
        "video_path": state.video_path,
        "qa_report": state.qa_report,
        "execution_trace": state.execution_trace,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    memory_writer.log(result)

    return {
        "status": result["status"],
        "video_path": result["video_path"],
        "qa_report": result["qa_report"],
        "execution_trace": result["execution_trace"],
    }
