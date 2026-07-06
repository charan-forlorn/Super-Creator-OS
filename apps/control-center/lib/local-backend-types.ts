/**
 * Stage 6.2 static types mirroring scos/control_center/backend_models.py.
 * No runtime behavior here -- these are display-only shapes for the static
 * Stage 6.2 mock panels. Nothing in this file calls fetch, opens a socket,
 * or reads a real clock.
 */

export type LocalBackendRequestType =
  | "health_check"
  | "command_preview"
  | "command_validate"
  | "command_enqueue_dry_run"
  | "session_snapshot"
  | "result_snapshot"
  | "approval_snapshot"
  | "project_state_snapshot";

export type LocalBackendResponseType =
  | "health"
  | "validation_result"
  | "dry_run_result"
  | "snapshot"
  | "rejected"
  | "error";

export type LocalBackendResponseStatus =
  | "success"
  | "rejected"
  | "blocked"
  | "failure";

export type BackendErrorKind =
  | "invalid_request_type"
  | "invalid_payload"
  | "forbidden_operation"
  | "unsafe_path"
  | "url_rejected"
  | "secret_metadata_rejected"
  | "unsupported_stage"
  | "command_not_allowed"
  | "backend_unavailable"
  | "contract_violation";

export type BackendWarningKind =
  | "dry_run_only"
  | "snapshot_mocked"
  | "persistence_not_enabled"
  | "event_stream_not_enabled"
  | "adapter_not_active";

export interface BackendErrorView {
  errorKind: BackendErrorKind;
  errorDetail: string;
  fieldName: string | null;
  recommendedAction: string;
}

export interface BackendWarningView {
  warningKind: BackendWarningKind;
  warningDetail: string;
  fieldName: string | null;
}

export interface LocalBackendRequestView {
  requestId: string;
  requestType: LocalBackendRequestType;
  operatorId: string;
  createdAt: string;
  payload: Record<string, string>;
}

export interface LocalBackendResponseView {
  ok: boolean;
  schemaVersion: number;
  requestId: string;
  requestType: LocalBackendRequestType;
  responseType: LocalBackendResponseType;
  status: LocalBackendResponseStatus;
  data: Record<string, string>;
  errors: BackendErrorView[];
  warnings: BackendWarningView[];
  createdAt: string;
}

export interface BackendHealthSnapshotView {
  schemaVersion: number;
  backendStatus: string;
  stage: string;
  capabilities: string[];
  disabledCapabilities: string[];
  activeStore: string;
  eventStreamStatus: string;
  adapterDispatchStatus: string;
}

export interface CommandApiActionView {
  id: string;
  label: string;
  description: string;
  request: LocalBackendRequestView;
  response: LocalBackendResponseView;
}
