/**
 * Stage 6.3 static mock data mirroring what
 * scos/control_center/state_snapshot.py would return over the SQLite WAL
 * store. All values are hand-authored constants -- no fetch, no timers, no
 * real clock/random/uuid, and no connection to a real database from the
 * frontend.
 */

import type {
  DurableApprovalRecordView,
  DurableCommandRecordView,
  DurableStateSnapshotView,
  DurableStateStatusView,
} from "./durable-state-types";

export const DURABLE_STATE_STATUS: DurableStateStatusView = {
  storeStatus: "ready_for_stage_6_4",
  stage: "Stage 6.3",
  dbPath: "scos/work/control_center/state/control_center.sqlite3",
  walMode: "enabled",
  eventStreamStatus: "disabled_until_stage_6_4",
  adapterDispatchStatus: "disabled_until_later_stage",
  backendSocketServerStatus: "disabled",
};

export const EXAMPLE_STATE_SNAPSHOT: DurableStateSnapshotView = {
  schemaVersion: 1,
  checkedAt: "2026-07-07T10:05:00Z",
  dbMode: "wal",
  walEnabled: true,
  dbPath: "scos/work/control_center/state/control_center.sqlite3",
  counts: {
    commands: 3,
    sessions: 2,
    events: 5,
    approvals: 1,
    results: 1,
  },
  disabledCapabilities: {
    websocket: "disabled",
    sse: "disabled",
    polling: "disabled",
    real_adapter_dispatch: "disabled",
    arbitrary_command_execution: "disabled",
    nextjs_api_routes: "disabled",
  },
  nextStage: "Stage 6.4 Real operator event stream / UI sync",
};

export const EXAMPLE_COMMAND_RECORD: DurableCommandRecordView = {
  commandId: "cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41",
  commandType: "command_enqueue_dry_run",
  status: "dry_run_enqueued",
  requestId: "req-health-001",
  sessionId: "session_7b3d1a9c4e6f2b58",
  createdAt: "2026-07-07T10:00:05Z",
  updatedAt: "2026-07-07T10:00:06Z",
};

export const EXAMPLE_APPROVAL_RECORD: DurableApprovalRecordView = {
  approvalId: "approval_4c8e21a7f3b96d0512e8a4c7f1b3d926",
  approvalType: "command_approval",
  subjectType: "command",
  subjectId: "cmd_1f6a9c2b8e4d7a53c0a19f7e6b2d5c41",
  decision: "approved",
  decidedBy: "operator-demo",
  decidedAt: "2026-07-07T10:01:00Z",
  reason: "Dry run only, no real execution",
};
