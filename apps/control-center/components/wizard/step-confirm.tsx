"use client";

import { WizardStep } from "@/components/wizard/wizard-step";

export function StepConfirm({ state }: Readonly<{ state: unknown }>) {
  const b = (state as { brief: Record<string, unknown> }).brief;
  return (
    <WizardStep id="wizard-confirm-title" title="5 · Confirm">
      <dl className="grid gap-2 text-xs text-ink-muted">
        <div><dt className="inline font-semibold text-ink">Title: </dt><dd className="inline">{String(b.projectTitle)}</dd></div>
        <div><dt className="inline font-semibold text-ink">Client/Brand: </dt><dd className="inline">{String(b.clientOrBrand)}</dd></div>
        <div><dt className="inline font-semibold text-ink">Purpose: </dt><dd className="inline">{String(b.projectPurpose)}</dd></div>
        <div><dt className="inline font-semibold text-ink">Duration: </dt><dd className="inline">{String(b.targetDurationSeconds)}s</dd></div>
        <div><dt className="inline font-semibold text-ink">Profiles: </dt><dd className="inline">{(b.outputProfiles as string[]).join(", ")}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-ink-muted">
        Confirming creates a draft in the authoritative local store. No render, materialization,
        or external action is triggered here.
      </p>
    </WizardStep>
  );
}
