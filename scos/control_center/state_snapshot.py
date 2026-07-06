"""SCOS Stage 6.3 durable Control Center state snapshot builder.

Builds a single deterministic dict summarizing the current durable state
(counts + latest records per table + WAL/mode verification + explicitly
disabled Stage 6.4+ capabilities) for display or handoff to a future event
stream. Never starts a server, never streams, never polls.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

from typing import Any

try:
    from .sqlite_state_store import SQLiteStateStore
    from .state_models import (
        CONTROL_CENTER_STATE_SCHEMA_VERSION,
        DurableStateError,
    )
    from .sqlite_state_schema import stable_json_dumps
except ImportError:  # direct-module execution (tests insert the package dir)
    from sqlite_state_store import SQLiteStateStore
    from state_models import (
        CONTROL_CENTER_STATE_SCHEMA_VERSION,
        DurableStateError,
    )
    from sqlite_state_schema import stable_json_dumps

STATE_SNAPSHOT_SCHEMA_VERSION = 1

_DISABLED_CAPABILITIES = {
    "websocket": "disabled",
    "sse": "disabled",
    "polling": "disabled",
    "real_adapter_dispatch": "disabled",
    "arbitrary_command_execution": "disabled",
    "nextjs_api_routes": "disabled",
}

_NEXT_STAGE = "Stage 6.4 Real operator event stream / UI sync"


def build_state_snapshot(
    store: SQLiteStateStore, *, checked_at: str
) -> dict | DurableStateError:
    if not isinstance(store, SQLiteStateStore):
        return DurableStateError.of(
            "invalid_payload", "store must be a SQLiteStateStore"
        )

    health = store.health_snapshot(checked_at=checked_at)
    if not health.get("ok", False):
        return DurableStateError.of(
            "storage_unavailable",
            str(health.get("error_detail", "state store unavailable")),
        )

    commands = store.list_commands()
    sessions = store.list_sessions()
    events = store.list_events()
    approvals = store.list_approvals()
    results = store.list_results()

    def _latest(records: tuple, limit: int = 5) -> list[dict[str, Any]]:
        return [record.to_dict() for record in records[-limit:]]

    return {
        "schema_version": STATE_SNAPSHOT_SCHEMA_VERSION,
        "state_schema_version": CONTROL_CENTER_STATE_SCHEMA_VERSION,
        "checked_at": checked_at,
        "db_mode": health.get("db_mode"),
        "wal_enabled": bool(health.get("wal_enabled", False)),
        "counts": {
            "commands": len(commands),
            "sessions": len(sessions),
            "events": len(events),
            "approvals": len(approvals),
            "results": len(results),
        },
        "latest_records": {
            "commands": _latest(commands),
            "sessions": _latest(sessions),
            "events": _latest(events),
            "approvals": _latest(approvals),
            "results": _latest(results),
        },
        "disabled_capabilities": dict(_DISABLED_CAPABILITIES),
        "next_stage": _NEXT_STAGE,
    }


def stable_state_snapshot_json(snapshot: dict) -> str:
    return stable_json_dumps(snapshot)
