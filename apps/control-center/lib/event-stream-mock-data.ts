/**
 * Stage 6.4 static mock data mirroring what
 * scos/control_center/event_stream_snapshot.py + ui_state_sync.py would
 * return over the Stage 6.3 durable SQLite WAL store. All values are
 * hand-authored constants -- no fetch, no timers, no real clock/random/uuid,
 * and no connection to a real backend from the frontend.
 */

import type {
  EventStreamRecordView,
  EventStreamSnapshotView,
} from "./event-stream-types";
import type { UIStateSyncSnapshotView } from "./ui-state-sync-types";

export const EXAMPLE_EVENT_RECORDS: EventStreamRecordView[] = [
  {
    eventId: "evt_command_created_0001",
    sequence: 1,
    eventType: "COMMAND_CREATED",
    source: "control_center",
    entityType: "command",
    entityId: "cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41",
    status: "queued",
    occurredAt: "2026-07-07T10:00:05Z",
    payload: { command_type: "command_enqueue_dry_run" },
    evidenceRefs: ["state:commands:cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41"],
  },
  {
    eventId: "evt_session_created_0002",
    sequence: 2,
    eventType: "SESSION_CREATED",
    source: "control_center",
    entityType: "session",
    entityId: "session_7b3d1a9c4e6f2b58",
    status: "working",
    occurredAt: "2026-07-07T10:00:20Z",
    payload: { task_id: "task-1", agent_id: "agent-1" },
    evidenceRefs: ["state:sessions:session_7b3d1a9c4e6f2b58"],
  },
  {
    eventId: "evt_approval_required_0003",
    sequence: 3,
    eventType: "APPROVAL_REQUIRED",
    source: "control_center",
    entityType: "command",
    entityId: "cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41",
    status: "blocked",
    occurredAt: "2026-07-07T10:00:45Z",
    payload: { approval_type: "command_approval" },
    evidenceRefs: ["state:approvals:approval_4c8e21a7f3b96d0512e8a4c7f1b3d926"],
  },
  {
    eventId: "evt_command_approved_0004",
    sequence: 4,
    eventType: "COMMAND_APPROVED",
    source: "operator-demo",
    entityType: "command",
    entityId: "cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41",
    status: "approved",
    occurredAt: "2026-07-07T10:01:00Z",
    payload: { decided_by: "operator-demo" },
    evidenceRefs: ["state:approvals:approval_4c8e21a7f3b96d0512e8a4c7f1b3d926"],
  },
  {
    eventId: "evt_ui_sync_ready_0005",
    sequence: 5,
    eventType: "UI_SYNC_READY",
    source: "control_center",
    entityType: "ui",
    entityId: "panel_event_stream",
    status: "ready",
    occurredAt: "2026-07-07T10:01:05Z",
    payload: {},
    evidenceRefs: [],
  },
];

export const EXAMPLE_EVENT_STREAM_SNAPSHOT: EventStreamSnapshotView = {
  schemaVersion: 1,
  snapshotId: "evt-snap-9a3c5e7f1b2d4a6c8e0f2b4d6a8c0e2f",
  generatedAt: "2026-07-07T10:01:10Z",
  cursor: "evt_ui_sync_ready_0005",
  eventCount: EXAMPLE_EVENT_RECORDS.length,
  events: EXAMPLE_EVENT_RECORDS,
  statusCounts: {
    queued: 1,
    working: 1,
    blocked: 1,
    approved: 1,
    ready: 1,
  },
  sourceCounts: {
    control_center: 4,
    "operator-demo": 1,
  },
  warnings: [],
};

export const EXAMPLE_UI_STATE_SYNC_SNAPSHOT: UIStateSyncSnapshotView = {
  schemaVersion: 1,
  syncId: "ui-sync-2b4d6a8c0e2f4a6c8e0f2b4d6a8c0e2f",
  generatedAt: "2026-07-07T10:01:10Z",
  stateSource: "scos.control_center.state_snapshot",
  syncStatus: "ready",
  activeStage: "6.4",
  activeTask: "event_stream_and_ui_sync_foundation",
  backendStatus: "ready",
  durableStateStatus: "ready",
  latestEventId: "evt_ui_sync_ready_0005",
  latestEventSequence: 5,
  pendingOperatorActions: [],
  blockers: [],
  warnings: [],
};
