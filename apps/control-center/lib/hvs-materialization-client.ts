/**
 * Cohort 10D — typed client transport for controlled HVS project
 * materialization.
 *
 * The browser is NEVER the authority (Cohort 10D §3): every read comes from
 * the same-origin authorative API, and every transition is confirmed by the
 * authoritative response before the UI advances. No optimistic state
 * advancement; no browser storage; no demo fallback; no HVS call from the
 * browser.
 *
 * Truth states the UI must render explicitly:
 *  NOT_REQUESTED | AUTHORIZATION_REQUIRED | AUTHORIZED | STARTING |
 *  MATERIALIZED | FAILED_CONFIRMED | OUTCOME_UNKNOWN | RECONCILIATION_REQUIRED
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type MaterializationTruthState =
  | "MATERIALIZATION_NOT_REQUESTED"
  | "MATERIALIZATION_AUTHORIZATION_REQUIRED"
  | "MATERIALIZATION_AUTHORIZED"
  | "MATERIALIZATION_STARTING"
  | "HVS_PROJECT_MATERIALIZED"
  | "MATERIALIZATION_FAILED_CONFIRMED"
  | "MATERIALIZATION_OUTCOME_UNKNOWN"
  | "MATERIALIZATION_RECONCILIATION_REQUIRED";

export type MaterializationApiOutcome =
  | "success"
  | "rejected"
  | "failed"
  | "unknown";

export interface MaterializationPlanView {
  plan_schema_version: number;
  project_id: string;
  project_revision: number;
  normalized_hvs_project_name: string;
  destination_identity: string;
  project_metadata: Record<string, unknown>;
  output_profiles: string[];
  expected_files: string[];
  forbidden_operations: string[];
  plan_hash: string;
}

export interface MaterializationAttemptView {
  attempt_id: string;
  project_id: string;
  project_revision: number;
  plan_hash: string;
  destination_identity: string;
  authorization_id: string;
  capability_id: string;
  state: MaterializationTruthState;
  hvs_calls: number;
  started_at: string | null;
  finished_at: string | null;
  outcome: string | null;
  error_code: string | null;
  error_detail: string | null;
  persisted_result: Record<string, unknown> | null;
}

export interface ProjectionView {
  project_id: string;
  truth_state: MaterializationTruthState;
  current_revision: number | null;
  plan: MaterializationPlanView | null;
  attempts: MaterializationAttemptView[];
}

export interface MaterializationResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  decision?: string;
  projection?: ProjectionView;
  attempt?: MaterializationAttemptView;
  result?: {
    ok: boolean;
    state: MaterializationTruthState;
    attempt_id: string;
    authorization_id: string | null;
    capability_id: string;
    hvs_calls: number;
    outcome: string | null;
    error_code: string | null;
    error_detail: string | null;
    persisted_result: Record<string, unknown> | null;
  };
  classification?: string;
}

export interface UseHvsMaterialization {
  loadState: "loading" | "ready" | "error";
  projection: ProjectionView | null;
  errorCode: string | null;
  detail: string | null;
  observedAt: string | null;
  pending: boolean;
  refresh: () => void;
  requestAuthorization: (projectId: string, projectRevision: number, confirmed: boolean) => Promise<MaterializationResponse>;
  execute: (projectId: string, projectRevision: number, authorizationId: string, capabilityId: string, attemptId: string) => Promise<MaterializationResponse>;
  reconcile: (attemptId: string) => Promise<MaterializationResponse>;
}

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;

function parseResponse(data: unknown): MaterializationResponse {
  if (!data || typeof data !== "object") {
    return { ok: false, error_code: "RESPONSE_MALFORMED", detail: "no body" };
  }
  const d = data as Record<string, unknown>;
  return {
    ok: Boolean(d.ok),
    error_code: (d.error_code as string | null) ?? null,
    detail: (d.detail as string | null) ?? null,
    decision: (d.decision as string | null) ?? undefined,
    projection: (d.projection as ProjectionView | undefined) ?? undefined,
    attempt: (d.attempt as MaterializationAttemptView | undefined) ?? undefined,
    result: (d.result as MaterializationResponse["result"] | undefined) ?? undefined,
    classification: (d.classification as string | undefined) ?? undefined,
  };
}

export function useHvsMaterialization(): UseHvsMaterialization {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [projection, setProjection] = useState<ProjectionView | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [pending, setPending] = useState<boolean>(false);
  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoadState("loading");
    fetch("/api/hvs-materialization/projection", { method: "GET", cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`http_${res.status}`);
        return res.json();
      })
      .then((payload: unknown) => {
        if (seq !== requestSeq.current) return;
        const env = parseResponse(payload);
        setProjection(env.projection ?? null);
        setErrorCode(env.error_code);
        setDetail(env.detail);
        setObservedAt(new Date().toISOString());
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        setProjection(null);
        setErrorCode("READ_FAILED");
        setDetail(err instanceof Error ? err.message : "unknown_error");
        setObservedAt(new Date().toISOString());
        setLoadState("ready");
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const requestAuthorization = useCallback(
    async (projectId: string, projectRevision: number, confirmed: boolean): Promise<MaterializationResponse> => {
      if (!projectIdSafe({ projectId })) {
        return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" };
      }
      setPending(true);
      try {
        const res = await fetch("/api/hvs-materialization/authorize", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ projectId, projectRevision, confirmed, authorizationId: `auth-${projectId}`, nonce: "n0", operatorId: "local-solo-operator" }),
        });
        const env = parseResponse(await res.json());
        if (env.ok) refresh();
        return env;
      } catch (err: unknown) {
        return { ok: false, error_code: "REQUEST_FAILED", detail: err instanceof Error ? err.message : "unknown_error" };
      } finally {
        setPending(false);
      }
    },
    [refresh],
  );

  const execute = useCallback(
    async (projectId: string, projectRevision: number, authorizationId: string, capabilityId: string, attemptId: string): Promise<MaterializationResponse> => {
      if (!projectIdSafe({ projectId })) {
        return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" };
      }
      setPending(true);
      try {
        const res = await fetch("/api/hvs-materialization/execute", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ projectId, projectRevision, authorizationId, capabilityId, attemptId, operatorId: "local-solo-operator" }),
        });
        const env = parseResponse(await res.json());
        if (env.ok) refresh();
        return env;
      } catch (err: unknown) {
        return { ok: false, error_code: "REQUEST_FAILED", detail: err instanceof Error ? err.message : "unknown_error" };
      } finally {
        setPending(false);
      }
    },
    [refresh],
  );

  const reconcile = useCallback(
    async (attemptId: string): Promise<MaterializationResponse> => {
      setPending(true);
      try {
        const res = await fetch("/api/hvs-materialization/reconcile", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ attemptId }),
        });
        const env = parseResponse(await res.json());
        if (env.ok) refresh();
        return env;
      } catch (err: unknown) {
        return { ok: false, error_code: "REQUEST_FAILED", detail: err instanceof Error ? err.message : "unknown_error" };
      } finally {
        setPending(false);
      }
    },
    [refresh],
  );

  return {
    loadState,
    projection,
    errorCode,
    detail,
    observedAt,
    pending,
    refresh,
    requestAuthorization,
    execute,
    reconcile,
  };
}

function projectIdSafe(body: unknown): boolean {
  const b = body as Record<string, unknown> | null;
  if (!b || typeof b.projectId !== "string") return false;
  return SAFE_ID_PATTERN.test(b.projectId);
}
