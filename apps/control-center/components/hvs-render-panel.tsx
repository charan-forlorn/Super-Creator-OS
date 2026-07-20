"use client";

import { useEffect, useState } from "react";
import {
  useHvsRender,
  exportRenderArtifact,
  type ExportResponse,
  type RenderTruthState,
} from "@/lib/hvs-render-client";
import { ConfirmationModal } from "@/components/confirmation-modal";

const REQUIRED_STATES: RenderTruthState[] = [
  "RENDER_NOT_REQUESTED",
  "RENDER_AUTHORIZATION_REQUIRED",
  "RENDER_AUTHORIZED",
  "RENDER_STARTING",
  "RENDER_RUNNING",
  "RENDER_SUCCEEDED",
  "RENDER_FAILED_CONFIRMED",
  "RENDER_OUTCOME_UNKNOWN",
  "RENDER_RECONCILIATION_REQUIRED",
];

function toneFor(state: RenderTruthState): string {
  if (state === "RENDER_SUCCEEDED") return "text-status-review";
  if (state === "RENDER_FAILED_CONFIRMED") return "text-status-failed";
  if (state === "RENDER_OUTCOME_UNKNOWN" || state === "RENDER_RECONCILIATION_REQUIRED")
    return "text-status-waiting";
  return "text-status-waiting";
}

function StatePill({ state }: Readonly<{ state: RenderTruthState }>) {
  return (
    <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${toneFor(state)}`}>
      {state}
    </span>
  );
}

function PlanCard({ plan }: Readonly<{ plan: import("@/lib/hvs-render-client").RenderPlan | null }>) {
  if (!plan) return null;
  return (
    <div className="mt-3 rounded-md border border-border-soft p-3 text-[12px]">
      <p className="font-semibold">Deterministic render plan</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-muted-foreground">Project identity</dt>
        <dd className="font-mono">{plan.project_id}</dd>
        <dt className="text-muted-foreground">Revision</dt>
        <dd className="font-mono">{plan.project_revision}</dd>
        <dt className="text-muted-foreground">HVS project</dt>
        <dd className="font-mono">{plan.hvs_project_name}</dd>
        <dt className="text-muted-foreground">Output root</dt>
        <dd className="font-mono break-all">{plan.output_root_identity}</dd>
        <dt className="text-muted-foreground">Operation</dt>
        <dd className="font-mono">RENDER_HVS_PROJECT</dd>
        <dt className="text-muted-foreground">Expected output</dt>
        <dd className="font-mono break-all">{plan.expected_output_relative_path}</dd>
        <dt className="text-muted-foreground">Plan fingerprint</dt>
        <dd className="font-mono break-all">{plan.plan_hash}</dd>
      </dl>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Forbidden operations: {(plan.forbidden_operations ?? []).join(", ")}
      </p>
      <p className="mt-1 text-[11px] font-semibold text-status-failed">
        No render starts automatically. Authorization is server-issued on explicit confirmation.
      </p>
    </div>
  );
}

function ArtifactCard({ attempt }: Readonly<{ attempt: import("@/lib/hvs-render-client").RenderAttemptView }>) {
  const art = attempt.artifact_descriptor;
  if (!art) return null;
  return (
    <div className="mt-3 rounded-md border border-border-soft p-3 text-[12px]">
      <p className="font-semibold">Validated artifact</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-muted-foreground">Filename</dt>
        <dd className="font-mono break-all">{art.filename}</dd>
        <dt className="text-muted-foreground">Media type</dt>
        <dd className="font-mono">{art.media_type}</dd>
        <dt className="text-muted-foreground">Size</dt>
        <dd className="font-mono">{art.size_bytes} bytes</dd>
        <dt className="text-muted-foreground">SHA-256</dt>
        <dd className="font-mono break-all">{art.sha256 ? `${art.sha256.slice(0, 16)}…` : "—"}</dd>
        <dt className="text-muted-foreground">Resolution</dt>
        <dd className="font-mono">{art.width ?? "?"}×{art.height ?? "?"}</dd>
        <dt className="text-muted-foreground">Duration</dt>
        <dd className="font-mono">{art.duration ?? "?"}s</dd>
        <dt className="text-muted-foreground">Validation</dt>
        <dd className="font-mono">{art.validation_state}</dd>
      </dl>
    </div>
  );
}

export function HvsRenderPanel({ projectId }: Readonly<{ projectId: string }>) {
  const r = useHvsRender();
  const [confirmed, setConfirmed] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [lastDetail, setLastDetail] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<ExportResponse | null>(null);

  useEffect(() => { r.refresh(projectId); }, [projectId, r.refresh]);

  const projection = r.projection;
  const state: RenderTruthState = projection?.truth_state ?? "RENDER_NOT_REQUESTED";
  const plan = projection?.plan ?? null;
  const revision = projection?.current_revision ?? 2;

  const trusted = r.loadState === "ready" && r.errorCode === null;
  const planHashValid = !!plan?.materialization_plan_hash && plan.materialization_plan_hash.length >= 8;
  const canAuthorize = trusted && planHashValid && (state === "RENDER_NOT_REQUESTED" || state === "RENDER_AUTHORIZATION_REQUIRED");
  const canExecute =
    trusted &&
    state !== "RENDER_STARTING" &&
    state !== "RENDER_RUNNING" &&
    state === "RENDER_AUTHORIZED" && Boolean(projection?.authorization?.authorization_id && projection.authorization.capability_id && projection.authorization.attempt_id);
  const canReconcile =
    trusted &&
    (state === "RENDER_OUTCOME_UNKNOWN" || state === "RENDER_RECONCILIATION_REQUIRED");

  async function onAuthorize() {
    if (submitted || r.pending) return;
    setSubmitted(true);
    const res = await r.requestAuthorization(
      projectId,
      revision,
      true,
      plan?.materialization_attempt_id ?? "",
      plan?.materialization_plan_hash ?? "",
      "vertical",
    );
    setLastDetail(res.detail ?? res.error_code ?? null);
    setSubmitted(false);
  }

  async function onExecuteConfirmed() {
    if (submitted || r.pending || !confirmed) return;
    setModalOpen(false);
    setSubmitted(true);
    const lastAttempt = projection?.attempts[projection.attempts.length - 1];
    const latestAuth = projection?.authorization;
    const authId = latestAuth?.authorization_id ?? lastAttempt?.authorization_id;
    const capId = latestAuth?.capability_id ?? lastAttempt?.capability_id;
    const attId = latestAuth?.attempt_id ?? lastAttempt?.attempt_id;
    if (!authId || !capId || !attId) { setLastDetail("authority identity missing"); setSubmitted(false); return; }
    const res = await r.execute(
      projectId,
      revision,
      authId,
      capId,
      attId,
      plan?.materialization_attempt_id ?? "",
      plan?.materialization_plan_hash ?? "",
      "vertical",
    );
    setLastDetail(res.detail ?? res.error_code ?? null);
    setSubmitted(false);
    setConfirmed(false);
  }

  async function onExport() {
    if (exporting) return;
    const lastAttempt = projection?.attempts[projection.attempts.length - 1];
    if (!lastAttempt?.attempt_id) { setExportResult({ ok: false, error_code: "ATTEMPT_ID_MISSING", detail: null, download_url: null, sha256: null }); return; }
    const attId = lastAttempt.attempt_id;
    setExporting(true);
    const res = await exportRenderArtifact(attId);
    setExportResult(res);
    setExporting(false);
  }

  async function onReconcile() {
    if (submitted || r.pending) return;
    setSubmitted(true);
    const lastAttempt = projection?.attempts[projection.attempts.length - 1];
    if (lastAttempt) {
      const res = await r.reconcile(lastAttempt.attempt_id);
      setLastDetail(res.detail ?? res.error_code ?? res.classification ?? null);
    }
    setSubmitted(false);
  }

  const lastAttempt = projection?.attempts[projection.attempts.length - 1];

  return (
    <section className="rounded-lg border border-border-soft p-4" aria-label="HVS project render">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">HVS Project Render (Controlled)</h2>
        <StatePill state={state} />
      </header>

      {r.loadState === "loading" && <p className="mt-2 text-[11px]">Reading authoritative local SCOS state…</p>}
      {!trusted && r.loadState === "ready" && (
        <p className="mt-2 text-[11px] font-semibold text-status-failed">Authoritative store unavailable — actions disabled.</p>
      )}

      {REQUIRED_STATES.includes(state) && (
        <p className="mt-1 text-[11px] text-muted-foreground">Truth state: {state}</p>
      )}

      {trusted && projection && !planHashValid && (
        <p className="mt-1 text-[11px] font-semibold text-status-failed">Render plan unavailable — authorization disabled until a valid plan hash is provided.</p>
      )}

      <PlanCard plan={plan} />

      <label className="mt-3 flex items-center gap-2 text-[12px]">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={!canExecute || r.pending}
          onChange={(e) => setConfirmed(e.target.checked)}
          aria-label="I confirm this authorized render"
        />
        Explicitly confirm this authorized render (single render only, no automatic retry)
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onAuthorize}
          disabled={!canAuthorize || submitted || r.pending}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          {r.pending && submitted ? "Working…" : "Request render authorization"}
        </button>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          disabled={!canExecute || submitted || r.pending}
          data-testid="execute-render"
          className="rounded-md border border-status-failed/50 bg-status-failed/10 px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          {r.pending && submitted ? "Rendering…" : "Execute render (single request)"}
        </button>
        <button
          type="button"
          onClick={onExport}
          disabled={exporting || state !== "RENDER_SUCCEEDED"}
          aria-disabled={exporting || state !== "RENDER_SUCCEEDED"}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          {exporting ? "Exporting…" : "Export package"}
        </button>
        <button
          type="button"
          onClick={onReconcile}
          disabled={!canReconcile || submitted || r.pending}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          Reconcile (read-only)
        </button>
      </div>

      {state === "RENDER_STARTING" && (
        <p className="mt-2 text-[11px] text-status-waiting">Starting — awaiting authoritative result (not yet confirmed).</p>
      )}
      {state === "RENDER_OUTCOME_UNKNOWN" && (
        <p className="mt-2 text-[11px] text-status-waiting">Outcome unknown. Run read-only reconciliation; do not retry.</p>
      )}
      {state === "RENDER_SUCCEEDED" && lastAttempt && (
        <p className="mt-2 text-[12px] font-semibold text-status-review">
          Render succeeded — attempt {lastAttempt.attempt_id}
        </p>
      )}
      {lastAttempt && state === "RENDER_SUCCEEDED" && <ArtifactCard attempt={lastAttempt} />}
      {lastDetail && <p className="mt-2 text-[11px] text-muted-foreground">Server: {lastDetail}</p>}

      {exportResult ? (
        <div className="mt-3 rounded-md border border-border-soft p-3 text-[12px]" role={exportResult.ok ? "status" : "alert"}>
          {exportResult.ok ? (
            <p className="font-semibold text-status-review">Export package ready</p>
          ) : (
            <p className="font-semibold text-status-failed">Export not available — {exportResult.error_code}</p>
          )}
          {exportResult.detail ? <p className="mt-1 text-muted-foreground">{exportResult.detail}</p> : null}
        </div>
      ) : null}

      <ConfirmationModal
        open={modalOpen}
        title="Confirm render execution"
        description="This starts a single, explicit render request. There is no automatic retry. Confirm only if you authorized this render."
        confirmLabel="Confirm render"
        disabled={!confirmed}
        disabledReason={!confirmed ? "Check the explicit confirmation box first." : undefined}
        pending={r.pending || submitted}
        onConfirm={onExecuteConfirmed}
        onCancel={() => setModalOpen(false)}
      />
    </section>
  );
}

export default HvsRenderPanel;
