/**
 * Stage 6.4 static types mirroring scos/control_center/event_stream_models.py.
 * No runtime behavior here -- these are display-only shapes for the static
 * Stage 6.4 mock panels. Nothing in this file calls fetch, opens a socket,
 * reads a real clock, or generates a random id.
 */

export type EventStreamEventType =
  | "COMMAND_CREATED"
  | "COMMAND_APPROVED"
  | "COMMAND_REJECTED"
  | "COMMAND_COMPLETED"
  | "COMMAND_BLOCKED"
  | "SESSION_CREATED"
  | "SESSION_UPDATED"
  | "RESULT_READY"
  | "APPROVAL_REQUIRED"
  | "STATE_SNAPSHOT_CREATED"
  | "BACKEND_HEALTH_CHANGED"
  | "DURABLE_STATE_CHANGED"
  | "UI_SYNC_READY";

export type EventStreamStatus =
  | "queued"
  | "working"
  | "ready"
  | "blocked"
  | "approved"
  | "rejected"
  | "completed"
  | "failed"
  | "stale"
  | "unknown";

export interface EventStreamRecordView {
  eventId: string;
  sequence: number;
  eventType: EventStreamEventType;
  source: string;
  entityType: string;
  entityId: string;
  status: EventStreamStatus;
  occurredAt: string;
  payload: Record<string, string>;
  evidenceRefs: string[];
}

export interface EventStreamSnapshotView {
  schemaVersion: number;
  snapshotId: string;
  generatedAt: string;
  cursor: string;
  eventCount: number;
  events: EventStreamRecordView[];
  statusCounts: Record<string, number>;
  sourceCounts: Record<string, number>;
  warnings: string[];
}
