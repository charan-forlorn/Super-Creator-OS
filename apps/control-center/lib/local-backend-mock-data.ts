/**
 * Stage 6.2 static mock data mirroring what
 * scos/control_center/local_backend.py would return. All values are
 * hand-authored constants -- no fetch, no timers, no real clock/random.
 */

import type {
  BackendHealthSnapshotView,
  CommandApiActionView,
} from "./local-backend-types";

export const BACKEND_HEALTH_SNAPSHOT: BackendHealthSnapshotView = {
  schemaVersion: 1,
  backendStatus: "ready",
  stage: "Stage 6.2",
  capabilities: [
    "health_check",
    "command_preview",
    "command_validate",
    "command_enqueue_dry_run",
  ],
  disabledCapabilities: [
    "sqlite_wal_persistence",
    "websocket_stream",
    "server_sent_events",
    "polling",
    "real_adapter_dispatch",
    "arbitrary_command_execution",
  ],
  activeStore: "in_memory_only",
  eventStreamStatus: "disabled_until_stage_6_4",
  adapterDispatchStatus: "disabled_until_later_stage",
};

export const COMMAND_API_ACTIONS: CommandApiActionView[] = [
  {
    id: "health-check",
    label: "Health Check",
    description: "Reports the Stage 6.2 backend capability snapshot. Never fails.",
    request: {
      requestId: "req-health-001",
      requestType: "health_check",
      operatorId: "operator-demo",
      createdAt: "2026-07-07T10:00:00Z",
      payload: {},
    },
    response: {
      ok: true,
      schemaVersion: 1,
      requestId: "req-health-001",
      requestType: "health_check",
      responseType: "health",
      status: "success",
      data: {
        backend_status: "ready",
        stage: "Stage 6.2",
        active_store: "in_memory_only",
        event_stream_status: "disabled_until_stage_6_4",
        adapter_dispatch_status: "disabled_until_later_stage",
      },
      errors: [],
      warnings: [],
      createdAt: "2026-07-07T10:00:00Z",
    },
  },
  {
    id: "preview-command",
    label: "Preview Command",
    description:
      "Describes what a command would look like using the Stage 5.1 command contract. No execution.",
    request: {
      requestId: "req-preview-001",
      requestType: "command_preview",
      operatorId: "operator-demo",
      createdAt: "2026-07-07T10:01:00Z",
      payload: { command_type: "RUN_SMOKE_CHECK" },
    },
    response: {
      ok: true,
      schemaVersion: 1,
      requestId: "req-preview-001",
      requestType: "command_preview",
      responseType: "validation_result",
      status: "success",
      data: {
        command_type: "RUN_SMOKE_CHECK",
        would_be_valid: "True",
      },
      errors: [],
      warnings: [
        {
          warningKind: "dry_run_only",
          warningDetail: "preview does not execute or enqueue the command",
          fieldName: null,
        },
      ],
      createdAt: "2026-07-07T10:01:00Z",
    },
  },
  {
    id: "validate-command",
    label: "Validate Command",
    description:
      "Runs the full Stage 5.1 command contract check (type, args, forbidden text). No execution.",
    request: {
      requestId: "req-validate-001",
      requestType: "command_validate",
      operatorId: "operator-demo",
      createdAt: "2026-07-07T10:02:00Z",
      payload: { command_type: "RUN_STAGE4_FINAL_GATE", checked_at: "2026-07-07T10:00:00Z" },
    },
    response: {
      ok: true,
      schemaVersion: 1,
      requestId: "req-validate-001",
      requestType: "command_validate",
      responseType: "validation_result",
      status: "success",
      data: {
        command_type: "RUN_STAGE4_FINAL_GATE",
        valid: "True",
      },
      errors: [],
      warnings: [],
      createdAt: "2026-07-07T10:02:00Z",
    },
  },
  {
    id: "dry-run-enqueue",
    label: "Dry-run Enqueue",
    description:
      "Shows what would be enqueued. Never writes to the real Stage 5.1 command queue.",
    request: {
      requestId: "req-dryrun-001",
      requestType: "command_enqueue_dry_run",
      operatorId: "operator-demo",
      createdAt: "2026-07-07T10:03:00Z",
      payload: { command_type: "RUN_SMOKE_CHECK" },
    },
    response: {
      ok: true,
      schemaVersion: 1,
      requestId: "req-dryrun-001",
      requestType: "command_enqueue_dry_run",
      responseType: "dry_run_result",
      status: "success",
      data: {
        would_enqueue: "True",
        command_type: "RUN_SMOKE_CHECK",
      },
      errors: [],
      warnings: [
        {
          warningKind: "dry_run_only",
          warningDetail: "no real command queue write occurred",
          fieldName: null,
        },
        {
          warningKind: "persistence_not_enabled",
          warningDetail: "Stage 6.2 has no SQLite/database-backed persistence",
          fieldName: null,
        },
      ],
      createdAt: "2026-07-07T10:03:00Z",
    },
  },
];

/**
 * A rejected example: an unknown/unsafe command type is blocked before any
 * handler runs. Shown in the UI as the "what rejection looks like" case.
 */
export const REJECTED_COMMAND_EXAMPLE: CommandApiActionView = {
  id: "rejected-example",
  label: "Rejected: Unsafe Command",
  description:
    "An unknown command_type is rejected deterministically -- nothing is enqueued or executed.",
  request: {
    requestId: "req-rejected-001",
    requestType: "command_enqueue_dry_run",
    operatorId: "operator-demo",
    createdAt: "2026-07-07T10:04:00Z",
    payload: { command_type: "DELETE_EVERYTHING" },
  },
  response: {
    ok: false,
    schemaVersion: 1,
    requestId: "req-rejected-001",
    requestType: "command_enqueue_dry_run",
    responseType: "dry_run_result",
    status: "rejected",
    data: { would_enqueue: "False" },
    errors: [
      {
        errorKind: "command_not_allowed",
        errorDetail: "unknown command_type: 'DELETE_EVERYTHING'",
        fieldName: "command_type",
        recommendedAction:
          "use one of: RUN_SMOKE_CHECK, RUN_RELEASE_CHECK, RUN_SECURITY_SCAN, RUN_STAGE4_FINAL_GATE, OPEN_STAGE5_HANDOFF, GENERATE_STATUS_SNAPSHOT",
      },
    ],
    warnings: [],
    createdAt: "2026-07-07T10:04:00Z",
  },
};
