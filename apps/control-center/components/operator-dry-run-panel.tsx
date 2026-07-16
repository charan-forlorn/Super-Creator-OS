"use client";

import { useMemo, useState } from "react";

import {
  buildDryRunRequest,
  planOperatorDryRun,
  type OperatorDryRunOperation,
  type OperatorDryRunResponse,
} from "@/lib/operator-dry-run";

const operationLabels: Record<OperatorDryRunOperation, string> = {
  "inspect-project": "inspect-project — read-only lookup preview",
  "initialize-project": "initialize-project — creation preview only",
  "prepare-render": "prepare-render — render plan preview only",
};

function StatusBadge({ status }: { status: OperatorDryRunResponse["status"] }) {
  const tone = status === "READY" ? "text-status-review" : status === "INVALID" ? "text-status-failed" : "text-status-waiting";
  return <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${tone}`}>{status}</span>;
}

function buildPanelParameters({
  operation,
  projectId,
  title,
  language,
  renderProfile,
}: {
  operation: OperatorDryRunOperation;
  projectId: string;
  title: string;
  language: string;
  renderProfile: string;
}): Record<string, string> {
  const parameters: Record<string, string> = { project_id: projectId };
  if (operation === "initialize-project") {
    parameters.title = title;
    parameters.language = language;
  }
  if (operation === "prepare-render") {
    parameters.render_profile = renderProfile;
  }
  return parameters;
}

export function OperatorDryRunPanel() {
  const [operation, setOperation] = useState<OperatorDryRunOperation>("inspect-project");
  const [projectId, setProjectId] = useState("demo-project");
  const [title, setTitle] = useState("Demo Project");
  const [language, setLanguage] = useState("en");
  const [renderProfile, setRenderProfile] = useState("vertical");
  const [pending, setPending] = useState(false);
  const [backendUnavailable, setBackendUnavailable] = useState(false);
  const [response, setResponse] = useState<OperatorDryRunResponse>(() =>
    planOperatorDryRun(buildDryRunRequest("inspect-project", { project_id: "demo-project" })),
  );

  const parameters = useMemo<Record<string, string>>(() => {
    return buildPanelParameters({ operation, projectId, title, language, renderProfile });
  }, [operation, projectId, title, language, renderProfile]);

  const clientPreview = useMemo(() => planOperatorDryRun(buildDryRunRequest(operation, parameters)), [operation, parameters]);
  const invalid = clientPreview.status === "INVALID";

  async function submitPreview() {
    if (invalid || pending) return;
    setPending(true);
    setBackendUnavailable(false);
    try {
      const result = await fetch("/api/operator-dry-run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(buildDryRunRequest(operation, parameters)),
      });
      const data = (await result.json()) as OperatorDryRunResponse;
      setResponse(data);
    } catch {
      setBackendUnavailable(true);
      setResponse({ ...clientPreview, status: "UNAVAILABLE", reason_codes: ["BACKEND_ROUTE_UNAVAILABLE", "SIDE_EFFECTS_ZERO"] });
    } finally {
      setPending(false);
    }
  }

  const visible = backendUnavailable ? response : response ?? clientPreview;

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="operator-dry-run-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Dry run command surface</p>
          <h3 id="operator-dry-run-title" className="mt-1 text-sm font-semibold text-ink">Operator dry-run preview</h3>
          <p className="mt-1 max-w-2xl text-xs text-ink-muted">
            Select a bounded operation and preview what would happen. This surface never executes, renders, dispatches, writes approvals, or mutates state.
          </p>
        </div>
        <StatusBadge status={visible.status} />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Operation</span>
          <select
            aria-label="Dry run operation"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={operation}
            onChange={(event) => setOperation(event.target.value as OperatorDryRunOperation)}
          >
            {Object.entries(operationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project id</span>
          <input aria-label="Project id" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
        </label>
        {operation === "initialize-project" ? (
          <>
            <label className="block text-xs text-ink-muted">
              <span className="mb-1 block font-semibold text-ink">Title</span>
              <input aria-label="Project title" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label className="block text-xs text-ink-muted">
              <span className="mb-1 block font-semibold text-ink">Language</span>
              <select aria-label="Language" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={language} onChange={(event) => setLanguage(event.target.value)}>
                <option value="en">en</option>
                <option value="th">th</option>
              </select>
            </label>
          </>
        ) : null}
        {operation === "prepare-render" ? (
          <label className="block text-xs text-ink-muted">
            <span className="mb-1 block font-semibold text-ink">Render profile</span>
            <select aria-label="Render profile" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={renderProfile} onChange={(event) => setRenderProfile(event.target.value)}>
              <option value="vertical">vertical</option>
              <option value="standard">standard</option>
            </select>
          </label>
        ) : null}
      </div>

      {invalid ? <p role="alert" className="mt-3 text-xs text-status-failed">Invalid dry-run input: {clientPreview.reason_codes.join(", ")}</p> : null}

      <button
        type="button"
        className="mt-4 rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50"
        disabled={invalid || pending}
        onClick={submitPreview}
      >
        {pending ? "Preview pending..." : "Preview dry run"}
      </button>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Authorization</h4>
          <p className="mt-1 text-sm text-ink">{visible.authorization.status}</p>
          <p className="mt-1 text-[11px] text-ink-faint">{visible.authorization.reason_codes.join(", ") || "No authorization required for preview"}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Zero side effects</h4>
          <p className="mt-1 text-sm text-status-review">No side effects performed</p>
          <p className="mt-1 text-[11px] text-ink-faint">side_effects_performed = {String(visible.side_effects_performed)}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="text-xs font-semibold text-ink">Prerequisites</h4>
          <ul className="mt-2 space-y-1 text-xs text-ink-muted">
            {visible.prerequisites.map((item) => <li key={item.id}>{item.status}: {item.id} · {item.reason_code}</li>)}
          </ul>
        </div>
        <div>
          <h4 className="text-xs font-semibold text-ink">Reason codes</h4>
          <ul className="mt-2 space-y-1 text-xs text-ink-muted">
            {visible.reason_codes.map((code) => <li key={code}>{code}</li>)}
          </ul>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="text-xs font-semibold text-ink">Proposed actions (preview order)</h4>
          <ol className="mt-2 space-y-1 text-xs text-ink-muted">
            {visible.proposed_actions.map((item) => <li key={item.order}>{`${item.order}. ${item.action} → ${item.target}`}</li>)}
          </ol>
        </div>
        <div>
          <h4 className="text-xs font-semibold text-ink">Prohibited actions</h4>
          <ol className="mt-2 space-y-1 text-xs text-ink-muted">
            {visible.prohibited_actions.map((item) => <li key={item.order}>{`${item.order}. ${item.action}`}</li>)}
          </ol>
        </div>
      </div>

      {backendUnavailable ? <p role="alert" className="mt-4 text-xs text-status-waiting">Backend unavailable: showing deterministic unavailable dry-run response, not fake success.</p> : null}
    </section>
  );
}
