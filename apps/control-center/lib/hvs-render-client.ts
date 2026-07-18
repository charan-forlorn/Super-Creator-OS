/**
 * Cohort 10E — typed client transport for controlled HVS render execution.
 *
 * The browser is NEVER the authority: every read comes from the same-origin
 * authoritative API, and every transition is confirmed by the authoritative
 * response before the UI advances. No optimistic state advancement; no
 * browser storage; no demo fallback; no HVS call from the browser.
 *
 * Truth states the UI must render explicitly:
 *  NOT_REQUESTED | AUTHORIZATION_REQUIRED | AUTHORIZED | STARTING |
 *  RUNNING | SUCCEEDED | FAILED_CONFIRMED | OUTCOME_UNKNOWN |
 *  RECONCILIATION_REQUIRED
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  type RenderArtifactView,
  type RenderAttemptView,
  type RenderAuthorizationView,
  type RenderPlan,
  type RenderProjectionView,
  type RenderResponse,
  type RenderTruthState,
  buildAuthorizePayload,
  buildExecutePayload,
  buildProjectionPayload,
  buildReconcilePayload,
  HvsRenderStore,
  serverResolvedScope,
} from "@/lib/hvs-render-store";

export type {
  RenderArtifactView,
  RenderAttemptView,
  RenderAuthorizationView,
  RenderPlan,
  RenderProjectionView,
  RenderTruthState,
} from "@/lib/hvs-render-store";

export interface UseHvsRender {
  loadState: "loading" | "ready" | "error";
  projection: RenderProjectionView | null;
  errorCode: string | null;
  detail: string | null;
  observedAt: string | null;
  pending: boolean;
  refresh: () => void;
  requestAuthorization: (
    projectId: string,
    projectRevision: number,
    confirmed: boolean,
    materializationAttemptId: string,
    materializationPlanHash: string,
    renderProfileId: string,
    outputRootIdentity: string,
  ) => Promise<RenderResponse>;
  execute: (
    projectId: string,
    projectRevision: number,
    authorizationId: string,
    capabilityId: string,
    attemptId: string,
    materializationAttemptId: string,
    materializationPlanHash: string,
    renderProfileId: string,
    outputRootIdentity: string,
  ) => Promise<RenderResponse>;
  reconcile: (attemptId: string) => Promise<RenderResponse>;
}

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
const ID_PATTERN = /^[a-z0-9_-]{2,64}$/;

function projectIdSafe(body: unknown): boolean {
  const b = body as Record<string, unknown> | null;
  if (!b || typeof b.projectId !== "string") return false;
  return SAFE_ID_PATTERN.test(b.projectId);
}

function parseResponse(data: unknown): RenderResponse {
  if (!data || typeof data !== "object") {
    return { ok: false, error_code: "RESPONSE_MALFORMED", detail: "no body" };
  }
  const d = data as Record<string, unknown>;
  return {
    ok: Boolean(d.ok),
    error_code: (d.error_code as string | null) ?? null,
    detail: (d.detail as string | null) ?? null,
    decision: (d.decision as string | null) ?? undefined,
    state: (d.state as RenderTruthState | undefined) ?? undefined,
    attempt_id: (d.attempt_id as string | null) ?? undefined,
    authorization_id: (d.authorization_id as string | null) ?? undefined,
    capability_id: (d.capability_id as string | undefined) ?? undefined,
    render_calls: (d.render_calls as number | undefined) ?? undefined,
    hvs_calls: (d.hvs_calls as number | undefined) ?? undefined,
    outcome: (d.outcome as string | null) ?? undefined,
    error_detail: (d.error_detail as string | null) ?? undefined,
    persisted_result: (d.persisted_result as Record<string, unknown> | null | undefined) ?? undefined,
    artifact: (d.artifact as RenderArtifactView | null | undefined) ?? undefined,
    classification: (d.classification as string | undefined) ?? undefined,
    projection: (d.projection as RenderProjectionView | undefined) ?? undefined,
    authorization: (d.authorization as RenderAuthorizationView | undefined) ?? undefined,
  };
}

export function useHvsRender(): UseHvsRender {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [projection, setProjection] = useState<RenderProjectionView | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [pending, setPending] = useState<boolean>(false);
  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoadState("loading");
    fetch("/api/hvs-render/projection", { method: "GET", cache: "no-store" })
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
    async (
      projectId: string,
      projectRevision: number,
      confirmed: boolean,
      materializationAttemptId: string,
      materializationPlanHash: string,
      renderProfileId: string,
      outputRootIdentity: string,
    ): Promise<RenderResponse> => {
      if (!projectIdSafe({ projectId })) {
        return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" };
      }
      setPending(true);
      try {
        const res = await fetch("/api/hvs-render/authorize", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            projectId,
            projectRevision,
            confirmed,
            authorizationId: `auth-${projectId}`,
            nonce: "n0",
            operatorId: "local-solo-operator",
            materializationAttemptId,
            materializationPlanHash,
            renderProfileId,
            outputRootIdentity,
          }),
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
    async (
      projectId: string,
      projectRevision: number,
      authorizationId: string,
      capabilityId: string,
      attemptId: string,
      materializationAttemptId: string,
      materializationPlanHash: string,
      renderProfileId: string,
      outputRootIdentity: string,
    ): Promise<RenderResponse> => {
      if (!projectIdSafe({ projectId })) {
        return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id" };
      }
      setPending(true);
      try {
        const res = await fetch("/api/hvs-render/execute", {
          method: "POST",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            projectId,
            projectRevision,
            authorizationId,
            capabilityId,
            attemptId,
            operatorId: "local-solo-operator",
            materializationAttemptId,
            materializationPlanHash,
            renderProfileId,
            outputRootIdentity,
          }),
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
    async (attemptId: string): Promise<RenderResponse> => {
      setPending(true);
      try {
        const res = await fetch("/api/hvs-render/reconcile", {
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

export interface ExportResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  download_url: string | null;
  sha256: string | null;
}

/**
 * Phase 2 — Export the rendered artifact package.
 *
 * NOTE: a real Python export backend does not yet exist (the HVS adapter
 * allowlist forbids the export operation). The endpoint is a controlled,
 * fail-closed stub that returns a deterministic package envelope only when
 * explicitly enabled by the operator via SCOS_EXPORT_STUB_ENABLED. Otherwise
 * it refuses, so the UI export control stays inert (no fabricated success).
 */
export async function exportRenderArtifact(attemptId: string): Promise<ExportResponse> {
  try {
    const res = await fetch("/api/hvs-render/export", {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ attemptId }),
    });
    const data = (await res.json()) as Record<string, unknown>;
    return {
      ok: Boolean(data.ok),
      error_code: (data.error_code as string | null) ?? null,
      detail: (data.detail as string | null) ?? null,
      download_url: (data.download_url as string | null) ?? null,
      sha256: (data.sha256 as string | null) ?? null,
    };
  } catch (err: unknown) {
    return {
      ok: false,
      error_code: "REQUEST_FAILED",
      detail: err instanceof Error ? err.message : "unknown_error",
      download_url: null,
      sha256: null,
    };
  }
}
