"use client";

import { useMemo, useState } from "react";

import {
  approveSoloProjection,
  dispatchSoloProjection,
  initialSoloProjection,
  rejectSoloProjection,
  type SoloWorkflowRequest,
  type SoloWorkflowStatus,
} from "@/lib/solo-operator-workflow";

function Status({ status }: { status: SoloWorkflowStatus }) {
  const tone = status === "dry_run_succeeded" ? "text-status-review" : status === "blocked" || status === "rejected" ? "text-status-failed" : "text-status-waiting";
  return <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${tone}`}>{status}</span>;
}

export function SoloOperatorWorkflowPanel() {
  const [request, setRequest] = useState<SoloWorkflowRequest>({
    workflow: "video-production",
    project_id: "demo-project",
    title: "Demo Project",
    language: "en",
    render_profile: "vertical",
    idempotency_key: "demo-project-video-production",
  });
  const [projection, setProjection] = useState(() => initialSoloProjection(request));
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const preview = useMemo(() => initialSoloProjection(request), [request]);
  const validationErrors = preview.errors;
  const canSubmit = validationErrors.length === 0 && !pendingAction;
  const canApprove = projection.status === "approval_required" && !pendingAction;
  const canDispatch = projection.status === "approved" && !pendingAction;

  function update<K extends keyof SoloWorkflowRequest>(key: K, value: SoloWorkflowRequest[K]) {
    setRequest((current) => ({ ...current, [key]: value }));
  }

  function withPending(action: string, fn: () => void) {
    if (pendingAction) return;
    setPendingAction(action);
    fn();
    setPendingAction(null);
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="solo-workflow-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Cohort 10A control loop</p>
          <h3 id="solo-workflow-title" className="mt-1 text-sm font-semibold text-ink">Video-production request</h3>
          <p className="mt-1 max-w-2xl text-xs text-ink-muted">
            Dry-run only. Approval and dispatch are separate actions. Demo request - not repository durable state.
          </p>
          <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-status-review">
            Runtime memory only
          </p>
          <p className="mt-1 max-w-2xl text-[11px] text-ink-faint">
            This browser panel keeps state only while the component remains mounted. Refresh, remount, a fresh browser context, or server restart resets the demo request.
          </p>
        </div>
        <Status status={projection.status} />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project id</span>
          <input aria-label="Cohort 10A project id" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={request.project_id} onChange={(event) => update("project_id", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Title</span>
          <input aria-label="Cohort 10A title" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={request.title} onChange={(event) => update("title", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Idempotency key</span>
          <input aria-label="Cohort 10A idempotency key" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={request.idempotency_key} onChange={(event) => update("idempotency_key", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Language</span>
          <select aria-label="Cohort 10A language" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={request.language} onChange={(event) => update("language", event.target.value as SoloWorkflowRequest["language"])}>
            <option value="en">en</option>
            <option value="th">th</option>
          </select>
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Render profile</span>
          <select aria-label="Cohort 10A render profile" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={request.render_profile} onChange={(event) => update("render_profile", event.target.value as SoloWorkflowRequest["render_profile"])}>
            <option value="vertical">vertical</option>
            <option value="standard">standard</option>
          </select>
        </label>
      </div>

      {validationErrors.length ? <p role="alert" className="mt-3 text-xs text-status-failed">{validationErrors.join(", ")}</p> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50" disabled={!canSubmit} onClick={() => withPending("submit", () => setProjection(preview))}>
          Submit request
        </button>
        <button type="button" className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50" disabled={!canApprove} onClick={() => withPending("approve", () => setProjection((current) => approveSoloProjection(current)))}>
          Approve
        </button>
        <button type="button" className="rounded-lg border border-status-failed/50 bg-status-failed/10 px-4 py-2 text-sm font-semibold text-status-failed disabled:cursor-not-allowed disabled:opacity-50" disabled={!canApprove} onClick={() => withPending("reject", () => setProjection((current) => rejectSoloProjection(current)))}>
          Reject
        </button>
        <button type="button" className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50" disabled={!canDispatch} onClick={() => withPending("dispatch", () => setProjection((current) => dispatchSoloProjection(current)))}>
          Dispatch dry run
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Command</h4>
          <p className="mt-1 break-all text-xs text-ink-muted">{projection.command_id}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Approval</h4>
          <p className="mt-1 text-sm text-ink">{projection.approval_required ? "Required" : `${projection.approval_count} decision recorded`}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Result</h4>
          <p className="mt-1 text-sm text-ink">{projection.safe_result_summary ?? "No result yet"}</p>
          <p className="mt-1 text-[11px] text-ink-faint">side_effects_performed = {String(projection.side_effects_performed)}</p>
        </div>
      </div>
    </section>
  );
}
