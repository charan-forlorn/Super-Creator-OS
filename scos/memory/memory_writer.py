"""Appends one JSON record per pipeline run to scos/memory/runs.json.

Separate from integrations/learning/memory_writer.py's safe_append (which guards
memory/database.json) — this is the new, self-contained per-run execution log this
module owns.
"""

from __future__ import annotations

import json
import os

RUNS_LOG_PATH = os.path.join(os.path.dirname(__file__), "runs.json")


def log(result: dict, runs_log_path: str = RUNS_LOG_PATH) -> dict:
    if os.path.exists(runs_log_path):
        with open(runs_log_path, "r", encoding="utf-8") as f:
            runs = json.load(f)
    else:
        runs = []

    entry = {
        "input": result["input_prompt"],
        "output_summary": {
            "status": result["status"],
            "video_path": result.get("video_path"),
        },
        "qa_result": result.get("qa_report"),
        "timestamp": result["timestamp"],
    }
    runs.append(entry)

    with open(runs_log_path, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)

    return entry
