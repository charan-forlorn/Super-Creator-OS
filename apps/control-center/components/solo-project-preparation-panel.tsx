"use client";

import { useState } from "react";

import {
  ACTUAL_DURABILITY_CLASS,
  OUTPUT_PROFILES,
  approvePreparationRequest,
  generatePreparationPreview,
  prepareProjectDraft,
  type OutputProfileId,
  type PreparationWorkflowProjection,
  type SoloProjectDraftInput,
} from "@/lib/solo-project-preparation";

const initialDraft: SoloProjectDraftInput = {
  projectTitle: "",
  clientOrBrand: "",
  projectPurpose: "",
  contentBrief: "",
  targetDurationSeconds: 30,
  outputProfiles: ["vertical_9_16"],
  operatorNotes: "",
};

const initialProjection: PreparationWorkflowProjection = {
  ok: true,
  state: "DRAFT",
  durabilityClass: ACTUAL_DURABILITY_CLASS,
  project: null,
  approvalProjectIdentity: null,
  approvalCount: 0,
  previewCount: 0,
  preview: null,
  errors: [],
};

function StatusPill({ state }: Readonly<{ state: PreparationWorkflowProjection["state"] }>) {
  const tone =
    state === "PREPARATION_PREVIEW_READY" || state === "APPROVED"
      ? "text-status-review"
      : state === "VALIDATION_FAILED"
        ? "text-status-failed"
        : "text-status-waiting";
  return <span className={`rounded-full border border-border-soft px-2 py-0.5 text-[10px] font-semibold ${tone}`}>{state}</span>;
}

export function SoloProjectPreparationPanel() {
  const [draft, setDraft] = useState<SoloProjectDraftInput>(initialDraft);
  const [projection, setProjection] = useState<PreparationWorkflowProjection>(initialProjection);
  const [approvalIdentity, setApprovalIdentity] = useState("");

  const canApprove = projection.state === "APPROVAL_REQUIRED" || projection.state === "APPROVED" || projection.state === "PREPARATION_PREVIEW_READY";
  const canPreview = projection.state === "APPROVED" || projection.state === "PREPARATION_PREVIEW_READY";

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

  function validateDraft() {
    const next = prepareProjectDraft(draft);
    setProjection(next);
    setApprovalIdentity(next.project?.projectIdentity ?? "");
  }

  function approveDraft() {
    setProjection((current) => approvePreparationRequest(current, approvalIdentity));
  }

  function generatePreview() {
    setProjection((current) => generatePreparationPreview(current, current.project?.projectIdentity ?? approvalIdentity));
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="solo-project-preparation-title" aria-label="Solo project preparation">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Cohort 10B planning surface</p>
          <h3 id="solo-project-preparation-title" className="mt-1 text-sm font-semibold text-ink">Project draft and render-preparation preview</h3>
          <p className="mt-1 max-w-2xl text-xs text-ink-muted">
            Prepare a project draft, record exact local approval, then generate a dry-run preparation preview. No HVS project, render artifact, upload, or publish action is created.
          </p>
          <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-status-review">Runtime memory only</p>
          <p className="mt-1 max-w-2xl text-[11px] text-ink-faint">
            Refresh, remount, a fresh browser context, or server restart resets this draft. This is not repository durable project data.
          </p>
        </div>
        <StatusPill state={projection.state} />
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project title</span>
          <input aria-label="Project title" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={draft.projectTitle} onChange={(event) => update("projectTitle", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Client or brand</span>
          <input aria-label="Client or brand" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={draft.clientOrBrand} onChange={(event) => update("clientOrBrand", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Project purpose</span>
          <input aria-label="Project purpose" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={draft.projectPurpose} onChange={(event) => update("projectPurpose", event.target.value)} />
        </label>
        <label className="block text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Target duration seconds</span>
          <input aria-label="Target duration seconds" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" min={5} max={600} type="number" value={draft.targetDurationSeconds} onChange={(event) => update("targetDurationSeconds", Number(event.target.value))} />
        </label>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <span className="mb-1 block font-semibold text-ink">Content brief</span>
          <textarea aria-label="Content brief" className="min-h-24 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={draft.contentBrief} onChange={(event) => update("contentBrief", event.target.value)} />
        </label>
        <fieldset className="lg:col-span-2">
          <legend className="mb-2 text-xs font-semibold text-ink">Output profiles</legend>
          <div className="flex flex-wrap gap-2">
            {OUTPUT_PROFILES.map((profile) => (
              <label key={profile.id} className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-border-soft bg-surface-2 px-3 py-2 text-xs font-semibold text-ink">
                <input aria-label={profile.label} type="checkbox" checked={draft.outputProfiles.includes(profile.id)} onChange={() => toggleProfile(profile.id)} />
                {profile.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <span className="mb-1 block font-semibold text-ink">Operator notes</span>
          <textarea aria-label="Operator notes" className="min-h-16 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={draft.operatorNotes} onChange={(event) => update("operatorNotes", event.target.value)} />
        </label>
      </div>

      {projection.errors.length ? <p role="alert" className="mt-3 text-xs text-status-failed">{projection.errors.join(", ")}</p> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink" onClick={validateDraft}>
          Validate project draft
        </button>
        <label className="min-w-64 flex-1 text-xs text-ink-muted">
          <span className="mb-1 block font-semibold text-ink">Approval project identity</span>
          <input aria-label="Approval project identity" className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink" value={approvalIdentity} onChange={(event) => setApprovalIdentity(event.target.value)} />
        </label>
        <button type="button" className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50" disabled={!canApprove} onClick={approveDraft}>
          Record local approval
        </button>
        <button type="button" className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review disabled:cursor-not-allowed disabled:opacity-50" disabled={!canPreview} onClick={generatePreview}>
          Generate dry-run preparation preview
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Project identity</h4>
          <p data-testid="preparation-project-identity" className="mt-1 break-all text-xs text-ink-muted">{projection.project?.projectIdentity ?? "Not issued for current draft"}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Approval</h4>
          <p className="mt-1 text-sm text-ink">{projection.approvalProjectIdentity ? "Exact local approval recorded" : "Approval required after validation"}</p>
          <p className="mt-1 text-[11px] text-ink-faint">approval_count = {projection.approvalCount}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Dry-run preview</h4>
          <p className="mt-1 text-sm text-ink">{projection.preview ? "Dry-run preview available for future execution" : "No dry-run preview generated"}</p>
          <p className="mt-1 text-[11px] text-ink-faint">preview_count = {projection.previewCount}</p>
        </div>
      </div>

      {projection.project ? (
        <div className="mt-4 rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Preparation plan</h4>
          <p className="mt-2 text-xs text-ink-muted">{projection.project.normalizedBriefSummary}</p>
          <p className="mt-2 text-xs text-ink-muted">Planned rendition count: {projection.project.plannedRenditionCount}</p>
          <p className="mt-1 text-xs text-ink-muted">Selected profiles: {projection.project.outputProfiles.map((profile) => profile.label).join(", ")}</p>
        </div>
      ) : null}

      {projection.preview ? (
        <div className="mt-4 rounded-lg border border-border-soft bg-surface-2 p-3">
          <h4 className="text-xs font-semibold text-ink">Dry-run preparation result</h4>
          <ul aria-label="Expected preparation stages" className="mt-2 grid gap-1 text-xs text-ink-muted">
            {projection.preview.expected_preparation_stages.map((stage) => (
              <li key={stage}>{stage}</li>
            ))}
          </ul>
          <div className="mt-3 grid gap-1 text-[11px] text-ink-faint">
            <span>side_effects_performed = {String(projection.preview.side_effects_performed)}</span>
            <span>render_started = {String(projection.preview.render_started)}</span>
            <span>hvs_project_created = {String(projection.preview.hvs_project_created)}</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}
