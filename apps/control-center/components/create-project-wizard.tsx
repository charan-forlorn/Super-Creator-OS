"use client";

import { useEffect, useRef, useState } from "react";
import {
  WIZARD_STEPS,
  canAdvance,
  INITIAL_WIZARD_STATE,
  validateBrief,
  validateAssets,
  type WizardState,
  type WizardStep,
} from "@/lib/create-project-wizard";
import { useProjectPreparation } from "@/lib/project-preparation-client";
import { StepBrief } from "@/components/wizard/step-brief";
import { StepTemplate } from "@/components/wizard/step-template";
import { StepAssets } from "@/components/wizard/step-assets";
import { StepProfiles } from "@/components/wizard/step-profiles";
import { StepConfirm } from "@/components/wizard/step-confirm";
import type { OutputProfileId } from "@/lib/solo-project-preparation";

const STEP_LABELS: Record<WizardStep, string> = {
  brief: "Brief",
  template: "Template",
  assets: "Assets",
  profiles: "Profiles",
  confirm: "Confirm",
};

export function CreateProjectWizard() {
  const [state, setState] = useState<WizardState>(INITIAL_WIZARD_STATE);
  const [errors, setErrors] = useState<string[]>([]);
  const [transitionErrors, setTransitionErrors] = useState<string[]>([]);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const stepRef = useRef<HTMLDivElement | null>(null);
  const pp = useProjectPreparation();

  const idx = WIZARD_STEPS.indexOf(state.step);

  useEffect(() => {
    stepRef.current?.focus();
  }, [state.step]);

  function advance() {
    setErrors([]);
    const next = WIZARD_STEPS[Math.min(idx + 1, WIZARD_STEPS.length - 1)];
    setState((s) => ({ ...s, step: next }));
  }
  function back() {
    setErrors([]);
    const prev = WIZARD_STEPS[Math.max(idx - 1, 0)];
    setState((s) => ({ ...s, step: prev }));
  }

  function validateCurrent(): boolean {
    if (state.step === "brief") {
      const e = validateBrief(state);
      setErrors(e);
      return e.length === 0;
    }
    if (state.step === "assets") {
      const e = validateAssets(state);
      setErrors(e);
      return e.length === 0;
    }
    return true;
  }

  async function createDraft() {
    setTransitionErrors([]);
    const res = await pp.createDraft({
      projectTitle: state.brief.projectTitle,
      clientOrBrand: state.brief.clientOrBrand,
      projectPurpose: state.brief.projectPurpose,
      contentBrief: state.brief.contentBrief,
      targetDurationSeconds: state.brief.targetDurationSeconds,
      outputProfiles: state.brief.outputProfiles,
      operatorNotes: state.brief.operatorNotes,
    });
    if (!res.ok || !res.record) {
      setTransitionErrors([res.error_code ?? "CREATE_FAILED", res.detail ?? ""].filter(Boolean));
      return;
    }
    setCreatedId(res.record.project_id);
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4" aria-labelledby="cpw-title">
      <h2 id="cpw-title" className="text-base font-semibold text-ink">Create project</h2>

      <ol className="mt-3 flex flex-wrap gap-2" aria-label="Wizard progress">
        {WIZARD_STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === idx ? "step" : undefined}
            className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${i === idx ? "border-status-review text-status-review" : "border-border-soft text-ink-muted"}`}
          >
            {i + 1}. {STEP_LABELS[s]}
          </li>
        ))}
      </ol>

      <div className="mt-4" ref={stepRef} tabIndex={-1}>
        {state.step === "brief" ? (
          <StepBrief
            state={state}
            onField={(k, v) => setState((s) => ({ ...s, brief: { ...s.brief, [k]: v } }))}
          />
        ) : null}
        {state.step === "template" ? (
          <StepTemplate state={state} onTemplate={(id) => setState((s) => ({ ...s, templateId: id }))} />
        ) : null}
        {state.step === "assets" ? (
          <StepAssets
            state={state}
            onAssetRef={(v) => setState((s) => ({ ...s, assetRef: v }))}
            onBrandKit={(v) => setState((s) => ({ ...s, brandKitId: v }))}
          />
        ) : null}
        {state.step === "profiles" ? (
          <StepProfiles
            selected={state.brief.outputProfiles}
            onToggle={(id: OutputProfileId) =>
              setState((s) => {
                const has = s.brief.outputProfiles.includes(id);
                return {
                  ...s,
                  brief: {
                    ...s.brief,
                    outputProfiles: has
                      ? s.brief.outputProfiles.filter((p) => p !== id)
                      : [...s.brief.outputProfiles, id],
                  },
                };
              })
            }
          />
        ) : null}
        {state.step === "confirm" ? <StepConfirm state={state} /> : null}
      </div>

      {errors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">{errors.join(", ")}</p>
      ) : null}
      {transitionErrors.length ? (
        <p className="mt-3 text-xs text-status-failed" role="alert">{transitionErrors.join(" · ")}</p>
      ) : null}
      {createdId ? (
        <p className="mt-3 text-xs text-status-review" role="status">
          Draft created: {createdId}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          disabled={idx === 0}
          onClick={back}
        >
          Back
        </button>
        {state.step !== "confirm" ? (
          <button
            type="button"
            className="rounded-lg border border-border-soft bg-surface-2 px-4 py-2 text-sm font-semibold text-ink"
            disabled={!canAdvance(state)}
            onClick={() => { if (validateCurrent()) advance(); }}
          >
            Next
          </button>
        ) : (
          <button
            type="button"
            className="rounded-lg border border-status-review/50 bg-status-review/10 px-4 py-2 text-sm font-semibold text-status-review"
            onClick={createDraft}
          >
            Create draft
          </button>
        )}
      </div>
    </section>
  );
}
