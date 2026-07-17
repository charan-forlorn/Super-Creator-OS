"use client";

import { useState } from "react";
import {
  useHvsMaterialization,
  type MaterializationTruthState,
  type MaterializationPlanView,
} from "@/lib/hvs-materialization-client";

const REQUIRED_STATES: MaterializationTruthState[] = [
  "MATERIALIZATION_NOT_REQUESTED",
  "MATERIALIZATION_AUTHORIZATION_REQUIRED",
  "MATERIALIZATION_AUTHORIZED",
  "MATERIALIZATION_STARTING",
  "HVS_PROJECT_MATERIALIZED",
  "MATERIALIZATION_FAILED_CONFIRMED",
  "MATERIALIZATION_OUTCOME_UNKNOWN",
  "MATERIALIZATION_RECONCILIATION_REQUIRED",
];

function toneFor(state: MaterializationTruthState): string {
  if (state === "HVS_PROJECT_MATERIALIZED") return "text-status-review";
  if (state === "MATERIALIZATION_FAILED_CONFIRMED") return "text-status-failed";
  if (state === "MATERIALIZATION_OUTCOME_UNKNOWN" || state === "MATERIALIZATION_RECONCILIATION_REQUIRED")
    return "text-status-waiting";
  return "text-status-waiting";
}

function StatePill({ state }: Readonly<{ state: MaterializationTruthState }>) {
  return (
    <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${toneFor(state)}`}>
      {state}
    </span>
  );
}

function PlanCard({ plan }: Readonly<{ plan: MaterializationPlanView | null }>) {
  if (!plan) return null;
  return (
    <div className="mt-3 rounded-md border border-border-soft p-3 text-[12px]">
      <p className="font-semibold">Deterministic materialization plan</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-muted-foreground">Project identity</dt>
        <dd className="font-mono">{plan.project_id}</dd>
        <dt className="text-muted-foreground">Revision</dt>
        <dd className="font-mono">{plan.project_revision}</dd>
        <dt className="text-muted-foreground">HVS project</dt>
        <dd className="font-mono">{plan.normalized_hvs_project_name}</dd>
        <dt className="text-muted-foreground">Destination</dt>
        <dd className="font-mono break-all">{plan.destination_identity}</dd>
        <dt className="text-muted-foreground">Operation</dt>
        <dd className="font-mono">{plan.project_metadata.hvs_project_name ? "MATERIALIZE_HVS_PROJECT" : "MATERIALIZE_HVS_PROJECT"}</dd>
        <dt className="text-muted-foreground">Plan fingerprint</dt>
        <dd className="font-mono break-all">{plan.plan_hash}</dd>
      </dl>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Expected structure: {plan.expected_files.join(", ")}
      </p>
      <p className="mt-1 text-[11px] font-semibold text-status-failed">
        No render will start. Authorization is server-issued on explicit confirmation.
      </p>
    </div>
  );
}

export function HvsMaterializationPanel({ projectId }: Readonly<{ projectId: string }>) {
  const m = useHvsMaterialization();
  const [confirmed, setConfirmed] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [lastDetail, setLastDetail] = useState<string | null>(null);

  const projection = m.projection;
  const state: MaterializationTruthState =
    projection?.truth_state ?? "MATERIALIZATION_NOT_REQUESTED";
  const plan = projection?.plan ?? null;
  const revision = projection?.current_revision ?? 2;

  // Explicit-confirmation gate: the materialization action requires a
  // deliberate operator confirmation and is disabled for untrusted/stale
  // state. Double submission is prevented by the submitted flag + pending.
  const trusted = m.loadState === "ready" && m.errorCode === null;
  const canAuthorize = trusted && (state === "MATERIALIZATION_NOT_REQUESTED" || state === "MATERIALIZATION_AUTHORIZATION_REQUIRED");
  const canExecute =
    trusted &&
    state !== "MATERIALIZATION_STARTING" &&
    state !== "HVS_PROJECT_MATERIALIZED" &&
    (state === "MATERIALIZATION_AUTHORIZED" || state === "MATERIALIZATION_NOT_REQUESTED" || state === "MATERIALIZATION_FAILED_CONFIRMED");
  const canReconcile =
    trusted &&
    (state === "MATERIALIZATION_OUTCOME_UNKNOWN" || state === "MATERIALIZATION_RECONCILIATION_REQUIRED");

  async function onAuthorize() {
    if (submitted || m.pending) return;
    setSubmitted(true);
    const res = await m.requestAuthorization(projectId, revision, true);
    setLastDetail(res.detail ?? res.error_code ?? null);
    setSubmitted(false);
  }

  async function onExecute() {
    if (submitted || m.pending || !confirmed) return;
    setSubmitted(true);
    const res = await m.execute(projectId, revision, `auth-${projectId}`, "cap-1", "att-1");
    setLastDetail(res.detail ?? res.error_code ?? null);
    setSubmitted(false);
    setConfirmed(false);
  }

  async function onReconcile() {
    if (submitted || m.pending) return;
    setSubmitted(true);
    const lastAttempt = projection?.attempts[projection.attempts.length - 1];
    if (lastAttempt) {
      const res = await m.reconcile(lastAttempt.attempt_id);
      setLastDetail(res.detail ?? res.error_code ?? res.classification ?? null);
    }
    setSubmitted(false);
  }

  return (
    <section className="rounded-lg border border-border-soft p-4" aria-label="HVS project materialization">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">HVS Project Materialization</h2>
        <StatePill state={state} />
      </header>

      {m.loadState === "loading" && <p className="mt-2 text-[11px]">Reading authoritative local SCOS state…</p>}
      {!trusted && m.loadState === "ready" && (
        <p className="mt-2 text-[11px] font-semibold text-status-failed">Authoritative store unavailable — actions disabled.</p>
      )}

      {REQUIRED_STATES.includes(state) && (
        <p className="mt-1 text-[11px] text-muted-foreground">Truth state: {state}</p>
      )}

      <PlanCard plan={plan} />

      <label className="mt-3 flex items-center gap-2 text-[12px]">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={!canExecute || m.pending}
          onChange={(e) => setConfirmed(e.target.checked)}
          aria-label="I confirm this authorized materialization"
        />
        Explicitly confirm this authorized materialization (no render starts automatically)
      </label>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onAuthorize}
          disabled={!canAuthorize || submitted || m.pending}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          {m.pending && submitted ? "Working…" : "Request authorization"}
        </button>
        <button
          type="button"
          onClick={onExecute}
          disabled={!canExecute || !confirmed || submitted || m.pending}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          {m.pending && submitted ? "Materializing…" : "Materialize (single request)"}
        </button>
        <button
          type="button"
          onClick={onReconcile}
          disabled={!canReconcile || submitted || m.pending}
          className="rounded-md border border-border-soft px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40"
        >
          Reconcile (read-only)
        </button>
      </div>

      {state === "MATERIALIZATION_STARTING" && (
        <p className="mt-2 text-[11px] text-status-waiting">Starting — awaiting authoritative result (not yet confirmed).</p>
      )}
      {state === "MATERIALIZATION_OUTCOME_UNKNOWN" && (
        <p className="mt-2 text-[11px] text-status-waiting">Outcome unknown. Run read-only reconciliation; do not retry.</p>
      )}
      {state === "HVS_PROJECT_MATERIALIZED" && projection?.attempts.length ? (
        <p className="mt-2 text-[12px] font-semibold text-status-review">
          Materialized HVS project:{" "}
          {String(
            (projection.attempts[projection.attempts.length - 1].persisted_result as Record<string, unknown> | null)?.hvs_project_name ??
              plan?.normalized_hvs_project_name ??
              "",
          )}
        </p>
      ) : null}
      {lastDetail && <p className="mt-2 text-[11px] text-muted-foreground">Server: {lastDetail}</p>}
    </section>
  );
}

export default HvsMaterializationPanel;
