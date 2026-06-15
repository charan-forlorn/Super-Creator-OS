"""event_bus.py — minimal in-process pub/sub + append-only event log.

The learning layer is event-driven so future skills (Video Analyst, Pattern
Discovery, Retention Optimizer) can subscribe WITHOUT changing the loop. Events
are also persisted to a JSONL log for replay/audit.

Event schema (every event):
    {"event_type": str, "project_id": str, "timestamp": ISO8601, "metadata": dict}

Usage:
    bus = EventBus()                         # default log: integrations/learning/events.jsonl
    bus.subscribe("PROJECT_QA_FAILED", handler)
    bus.emit("PROJECT_RENDERED", project_id="p1", metadata={...})
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Callable

from validators import validate_event

DEFAULT_LOG = Path(__file__).resolve().parent / "events.jsonl"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class EventBus:
    def __init__(self, log_path: Path | None = None):
        self.log_path = Path(log_path) if log_path else DEFAULT_LOG
        self._subs: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable[[dict], None]) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    def emit(self, event_type: str, project_id: str, metadata: dict | None = None,
             timestamp: str | None = None) -> dict:
        ev = {
            "event_type": event_type,
            "project_id": project_id,
            "timestamp": timestamp or _now_iso(),
            "metadata": metadata or {},
        }
        errs = validate_event(ev)
        if errs:
            raise ValueError("invalid event: " + "; ".join(errs))
        # persist (append-only JSONL — never rewrites prior lines)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        # dispatch to subscribers (failures in one handler don't block others)
        for h in self._subs.get(event_type, []):
            try:
                h(ev)
            except Exception as e:  # noqa: BLE001
                self.emit_safe_error(event_type, project_id, str(e))
        return ev

    def emit_safe_error(self, src_event: str, project_id: str, msg: str) -> None:
        line = {
            "event_type": "RENDER_FAILURE_DETECTED",
            "project_id": project_id,
            "timestamp": _now_iso(),
            "metadata": {"handler_error_for": src_event, "error": msg},
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def replay(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(l) for l in self.log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
