/**
 * Stage 6.4 static types mirroring scos/control_center/ui_state_sync.py.
 * No runtime behavior here -- these are display-only shapes for the static
 * Stage 6.4 mock panels. Nothing in this file calls fetch, opens a socket,
 * reads a real clock, or generates a random id.
 */

import type { EventStreamStatus } from "./event-stream-types";

export interface UIStateSyncSnapshotView {
  schemaVersion: number;
  syncId: string;
  generatedAt: string;
  stateSource: string;
  syncStatus: EventStreamStatus;
  activeStage: string;
  activeTask: string;
  backendStatus: EventStreamStatus;
  durableStateStatus: EventStreamStatus;
  latestEventId: string;
  latestEventSequence: number;
  pendingOperatorActions: string[];
  blockers: string[];
  warnings: string[];
}
