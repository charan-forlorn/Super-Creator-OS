"""SCOS Stage 3.5 — per-style timeline construction.

Pure function, no I/O: assembles one LearningTimeline from a style's raw version
snapshots (from style_history.json) plus the LearningEvents already resolved to
belong to that style_id. Ordering is always explicit (sorted), never dict/JSON
load order, so output is deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_models import LearningTimeline  # noqa: E402


def build_timeline(style_id: str, version_snapshots: list, events: list) -> LearningTimeline:
    versions_sorted = tuple(
        sorted((dict(v) for v in version_snapshots), key=lambda v: v["version"])
    )
    events_sorted = tuple(
        sorted(
            events,
            key=lambda e: (
                e.timestamp if e.timestamp is not None else -1,
                e.event_type,
                e.run_id or "",
            ),
        )
    )
    current_version = versions_sorted[-1]["version"] if versions_sorted else None
    return LearningTimeline(
        style_id=style_id,
        versions=versions_sorted,
        events=events_sorted,
        current_version=current_version,
    )
