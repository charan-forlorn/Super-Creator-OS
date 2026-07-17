"use client";

import { useState } from "react";
import {
  OUTPUT_PROFILES,
  validateProjectDraft,
  type OutputProfileId,
  type SoloProjectDraftInput,
} from "@/lib/solo-project-preparation";
import {
  useProjectPreparation,
  type ProjectPreparationRecord,
  type TruthStatus,
} from "@/lib/project-preparation-client";

const initialDraft: SoloProjectDraftInput = {
  projectTitle: "",
  clientOrBrand: "",
  projectPurpose: "",
  contentBrief: "",
  targetDurationSeconds: 30,
  outputProfiles: ["vertical_9_16"],
  operatorNotes: "",
};

function StatusPill({ state }: Readonly<{ state: string }>) {
  const tone =
    state === "PREPARATION_PREVIEW_READY" || state === "APPROVED"
      ? "text-status-review"
      : state === "VALIDATION_FAILED"
        ? "text-status-failed"
        : "text-status-waiting";
  return (
    <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${tone}`}>
      {state}
    </span>
  );
}

function TruthBadge({ status }: Readonly<{ status: TruthStatus | null }>) {
  const text =
    status === "AVAILABLE_WITH_DATA"
      ? "Authoritative store · process-restart durable"
      : status === "EMPTY"
        ? "Authoritative store · empty (no records)"
        : status === "UNAVAILABLE"
          ? "Authoritative store unavailable"
          : status === "CORRUPT"
            ? "Authoritative store corrupt"
            : status === "INCOMPATIBLE_SCHEMA"
              ? "Authoritative schema incompatible"
              : "Authoritative store loading";
  return (
    <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-status-review">
      {text}
    </p>
  );
}

export function SoloProjectPreparationPanel() {
  const [draft, setDraft] = useState<SoloProjectDraftInput>(initialDraft);
  const [clientErrors, setClientErrors] = useState<string[]>([]);
  const [authoritative, setAuthoritative] = useState<ProjectPreparationRecord | null>(null);
  const [transitionErrors, setTransitionErrors] = useState<string[]>([]);
  const pp = useProjectPreparation();

  const record = authoritative ?? (pp.records.length > 0 ? pp.records[pp.records.length - 1] : null);
  const activeState = record?.state ?? "DRAFT";

  const canApprove =
    activeState === "APPROVAL_REQUIRED" ||
    activeState === "APPROVED" ||
    activeState === "PREPARATION_PREVIEW_READY";
  const canPreview =
    activeState === "APPROVED" || activeState === "PREPARATION_PREVIEW_READY";

  // Truth-state guard: disable transitions unless the authoritative store is
  // trusted (AVAILABLE_WITH_DATA or EMPTY with a usable record).
  const trusted =
    pp.truthStatus === "AVAILABLE_WITH_DATA" || pp.truthStatus === "EMPTY";

  function update<K extends keyof SoloProjectDraftInput>(key: K, value: SoloProjectDraftInput[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function toggleProfile(profileId: OutputProfileId) {
    setDraft((current) => {
      const selected = current.outputProfiles.includes(profileId)
        ? current.outputProfiles.filter((existing) => existing !== profileId)
        : [...current.outputProfiles, profileId];
      return { ...current, outputProfiles: selected };
    });
  }

  async function validateDraft() {
    const errors = validateProjectDraft(draft);
    setClientErrors(errors);
    if (errors.length > 0) {
      setAuthoritative(null);
      return;
    }
    setTransitionErrors([]);
    const res = await pp.createDraft({
      projectTitle: draft.projectTitle,
      clientOrBrand: draft.clientOrBrand,
      projectPurpose: draft.projectPurpose,
      contentBrief: draft.contentBrief,
      targetDurationSeconds: draft.targetDurationSeconds,
      outputProfiles: draft.outputProfiles,
      operatorNotes: draft.operatorNotes,
    });
    if (!res.ok || !res.record) {
      setTransitionErrors([res.error_code ?? "CREATE_FAILED", res.detail ?? ""].filter(Boolean));
      return;
    }
    // Authoritative response only.
    setAuthoritative(res.record);
    setClientErrors([]);
    setTransitionErrors([]);
  }

  async function approveDraft() {
    if (!record) return;
    setTransitionErrors([]);
    const res = await pp.approve(record.project_id, record.revision);
    if (!res.ok || !res.record) {
      setTransitionErrors([res.error_code ?? "APPROVE_FAILED", res.detail ?? ""].filter(Boolean));
      return;
    }
    setAuthoritative(res.record);
    setTransitionErrors([]);
  }

  async function generatePreview() {
    if (!record) return;
    setTransitionErrors([]);
    const res = await pp.createPreview(record.project_id, record.revision);
    if (!res.ok || !res.record) {
      setTransitionErrors([res.error_code ?? "PREVIEW_FAILED", res.detail ?? ""].filter(Boolean));
      return;
    }
    setAuthoritative(res.record);
    setTransitionErrors([]);
  }

  return (
    <section
      className="rounded-card border border-border bg-surface p-4"
      aria-labelledby="solo-project-preparation-title"
      aria-label="Solo project preparation"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Cohort 10C authoritative persistence
          </p>
          <h3 id="solo-project-preparation-title" className="mt-1 text-sm font-semibold text-ink">
            Project draft and render-preparation preview
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-ink-muted">
            Prepare a project draft, record exact local approval, then generate a dry-run
            preparation preview. Truth lives in an authoritative local store
            (memory/runtime/control-center/project-preparation-v1.json); a refresh, a fresh
            browser context, or a server restart recovers the exact state. No HVS
            project, render artifact, upload, or publish action is created.
          </p>
          <TruthBadge status={pp.truthStatus} />
        </div>
        {record ? <StatusPill state={record.state} /> : <StatusPill state={activeState} />}
      </div>

      {pp.loadState === "loading" ? (
        <p className="mt-4 text-xs text-ink-faint" role="status">
          Reading authoritative local SCOS state…
        </p>
      ) : null}

      {pp.truthStatus === "UNAVAILABLE" ? (
        <p className="mt-4 rounded-lg border border-status-failed/40 bg-status-failed/10 p-3 text-xs text-status-failed" role="alert">
          Authoritative store unavailable — transitions disabled. (Not empty; not fabricated.)
        </p>
      ) : null}

      {pp.truthStatus === "CORRUPT" ? (
        <p className="mt-4 rounded-lg border border-status-failed/40 bg-status-failed/10 p-3 text-xs text-status-failed" role="alert">
          Authoritative store corrupt — no rewrite. Transitions disabled. (code: {pp.errorCode})
        </p>
      ) : null}

      {pp.truthStatus === "INCOMPATIBLE_SCHEMA" ? (
        <p className="mt-4 rounded-lg border border-status-failed/40 bg-status-failed/10 p-3 text-xs text-status-failed" role="alert">
          Authoritative schema incompatible — no mutation, no downgrade. (code: {pp.errorCode})
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project title</span>
          <input
            aria-label="Project title"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={draft.projectTitle}
            disabled={!!record}
            onChange={(event) => update("projectTitle", event.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Client or brand</span>
          <input
            aria-label="Client or brand"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={draft.clientOrBrand}
            disabled={!!record}
            onChange={(event) => update("clientOrBrand", event.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project purpose</span>
          <input
            aria-label="Project purpose"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={draft.projectPurpose}
            disabled={!!record}
            onChange={(event) => update("projectPurpose", event.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Target duration seconds</span>
          <input
            aria-label="Target duration seconds"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            min={5}
            max={600}
            type="number"
            value={draft.targetDurationSeconds}
            disabled={!!record}
            onChange={(event) => update("targetDurationSeconds", Number(event.target.value))}
          />
        </label>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <span className="mb-1 block font-semibold text-ink">Content brief</span>
          <textarea
            aria-label="Content brief"
            className="min-h-24 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={draft.contentBrief}
            disabled={!!record}
            onChange={(event) => update("contentBrief", event.target.value)}
          />
        </label>
        <fieldset className="lg:col-span-2" disabled={!!record}>
          <legend className="mb-2 text-xs font-semibold text-ink">Output profiles</legend>
          <div className="flex flex-wrap gap-2">
            {OUTPUT_PROFILES.map((profile) => (
              <label
                key={profile.id}
                className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-border-soft bg-surface-2 px-3 py-2 text-xs font-semibold text-ink"
              >
                <input
                  aria-label={profile.label}
                  type="checkbox"
                  checked={draft.outputProfiles.includes(profile.id)}
                  onChange={() => toggleProfile(profile.id)}
                />
                {profile.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <span className="mb-1 block font-semibold text-ink">Operator notes</span>
          <textarea
            aria-label="Operator notes"
            className="min-h-16 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={draft.operatorNotes}
            disabled={!!record}
            onChange={(event) => update("operatorNotes", event.target.value)}
          />
        </label>
      </div>

      {clientErrors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">
          {clientErrors.join(", ")}
        </p>
      ) : null}
      {transitionErrors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">
          {transitionErrors.join(" · ")}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
          disabled={!!record || !trusted}
          onClick={validateDraft}
        >
          Validate and create draft
        </button>
        <button
          type="button"
          className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canApprove || !trusted}
          onClick={approveDraft}
        >
          Record local approval
        </button>
        <button
          type="button"
          className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!canPreview || !trusted}
          onClick={generatePreview}
        >
          Generate dry-run preparation preview
        </button>
        <button
          type="button"
          className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
          onClick={() => pp.refresh()}
        >
          Refresh authoritative state
        </button>
      </div>

      {record ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
            <h4 className="text-xs font-semibold text-ink">Project identity</h4>
            <p className="mt-1 break-all text-xs text-ink-muted">{record.project_id}</p>
          </div>
          <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
            <h4 className="text-xs font-semibold text-ink">Approval</h4>
            <p className="mt-1 text-sm text-ink">
              {record.approval.status === "approved"
                ? "Exact local approval recorded"
                : "Approval required after validation"}
            </p>
            <p className="mt-1 text-[11px] text-ink-faint">revision = {record.revision}</p>
          </div>
          <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
            <h4 className="text-xs font-semibold text-ink">Dry-run preview</h4>
            <p className="mt-1 text-sm text-ink">
              {record.preparation_preview
                ? "Dry-run preview available for future execution"
                : "No dry-run preview generated"}
            </p>
            <p className="mt-1 text-[11px] text-ink-faint">
              preview_count = {record.preparation_preview ? 1 : 0}
            </p>
          </div>
        </div>
      ) : null}

      {record?.normalized ? (
        <div className="mt-4 rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Preparation plan</h4>
          <p className="mt-2 text-xs text-ink-muted">{record.normalized.normalized_brief_summary}</p>
          <p className="mt-2 text-xs text-ink-muted">
            Planned rendition count: {record.normalized.planned_rendition_count}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            Selected profiles: {record.normalized.output_profiles.map((profile) => profile.label).join(", ")}
          </p>
        </div>
      ) : null}

      {record?.preparation_preview ? (
        <div className="mt-4 rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Dry-run preparation result</h4>
          <ul
            aria-label="Expected preparation stages"
            className="mt-2 grid gap-1 text-xs text-ink-muted"
          >
            {record.preparation_preview.expected_preparation_stages.map((stage) => (
              <li key={stage}>{stage}</li>
            ))}
          </ul>
          <div className="mt-3 grid gap-1 text-[11px] text-ink-faint">
            <span>side_effects_performed = {String(record.preparation_preview?.approval_status ? record.side_effect_flags.side_effects_performed : record.side_effect_flags.side_effects_performed)}</span>
            <span>render_started = {String(record.side_effect_flags.render_started)}</span>
            <span>hvs_project_created = {String(record.side_effect_flags.hvs_project_created)}</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}
