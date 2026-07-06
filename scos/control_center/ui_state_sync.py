"""SCOS Stage 6.4 UI state sync snapshot builder.

Combines a Stage 6.3 durable state snapshot (``state_snapshot.build_state_snapshot``)
and a Stage 6.4 event stream snapshot (``event_stream_snapshot``) into a single
deterministic ``UIStateSyncSnapshot`` for Control Center static/local UI panels.

This is a snapshot/summary builder only. It never opens a socket, starts a
server, polls, sets a timer, or reads the system clock -- all "freshness"
comparisons are made against caller-supplied timestamp strings.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no WebSocket, no SSE, no polling, no timers.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        UI_STATE_SYNC_SCHEMA_VERSION,
        EventStreamSnapshot,
        UIStateSyncSnapshot,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from event_stream_models import (
        ALLOWED_EVENT_STATUSES,
        UI_STATE_SYNC_SCHEMA_VERSION,
        EventStreamSnapshot,
        UIStateSyncSnapshot,
    )


class UIStateSyncBuilderError(ValueError):
    """Raised when the supplied local snapshots cannot be combined."""


def _sha256_sync_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"ui-sync-{digest[:32]}"


def _backend_status_from_state(state_snapshot: dict[str, Any]) -> str:
    if not isinstance(state_snapshot, dict):
        return "unknown"
    if state_snapshot.get("db_mode") and state_snapshot.get("wal_enabled"):
        return "ready"
    if state_snapshot.get("db_mode"):
        return "working"
    return "unknown"


def _durable_state_status(state_snapshot: dict[str, Any]) -> str:
    if not isinstance(state_snapshot, dict):
        return "unknown"
    if state_snapshot.get("wal_enabled"):
        return "ready"
    return "blocked"


def build_ui_state_sync_snapshot(
    state_snapshot: dict[str, Any],
    event_snapshot: EventStreamSnapshot,
    *,
    generated_at: str,
    active_stage: str,
    active_task: str,
    state_source: str = "scos.control_center.state_snapshot",
    stale_if_state_checked_before: str | None = None,
    pending_operator_actions: Any = (),
    extra_blockers: Any = (),
) -> UIStateSyncSnapshot:
    """Build a deterministic ``UIStateSyncSnapshot`` from local snapshots only.

    ``stale_if_state_checked_before`` is an optional caller-supplied ISO-8601
    timestamp string; if the durable state snapshot's own ``checked_at`` is
    lexicographically smaller (i.e. earlier), the sync is marked ``stale``.
    No clock is ever read to determine this -- both timestamps come from the
    caller.
    """
    if not str(generated_at).strip():
        raise UIStateSyncBuilderError("generated_at must not be empty")
    if not isinstance(event_snapshot, EventStreamSnapshot):
        raise UIStateSyncBuilderError(
            "event_snapshot must be an EventStreamSnapshot"
        )
    if not isinstance(state_snapshot, dict):
        raise UIStateSyncBuilderError("state_snapshot must be a dict")

    warnings: list[str] = list(event_snapshot.warnings)
    blockers: list[str] = list(extra_blockers or ())

    backend_status = _backend_status_from_state(state_snapshot)
    durable_state_status = _durable_state_status(state_snapshot)

    if durable_state_status != "ready":
        blockers.append("durable_state_store_not_ready")
    if backend_status == "unknown":
        blockers.append("backend_health_unknown")

    sync_status = "ready"
    state_checked_at = str(state_snapshot.get("checked_at", ""))
    if (
        stale_if_state_checked_before
        and state_checked_at
        and state_checked_at < str(stale_if_state_checked_before)
    ):
        sync_status = "stale"
        warnings.append("durable_state_snapshot_older_than_expected")
    elif blockers:
        sync_status = "blocked"

    latest_event_id = ""
    latest_event_sequence = 0
    if event_snapshot.events:
        latest = event_snapshot.events[-1]
        latest_event_id = latest.event_id
        latest_event_sequence = latest.sequence

    sync_id = _sha256_sync_id(
        generated_at,
        event_snapshot.snapshot_id,
        state_checked_at,
        active_stage,
        active_task,
    )

    return UIStateSyncSnapshot(
        schema_version=UI_STATE_SYNC_SCHEMA_VERSION,
        sync_id=sync_id,
        generated_at=generated_at,
        state_source=state_source,
        sync_status=sync_status,
        active_stage=active_stage,
        active_task=active_task,
        backend_status=backend_status,
        durable_state_status=durable_state_status,
        latest_event_id=latest_event_id,
        latest_event_sequence=latest_event_sequence,
        pending_operator_actions=tuple(pending_operator_actions or ()),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
