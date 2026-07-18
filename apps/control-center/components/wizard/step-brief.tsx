"use client";

import { WizardStep, FieldLabel } from "@/components/wizard/wizard-step";
import type { WizardState } from "@/lib/create-project-wizard";

export function StepBrief({
  state,
  onField,
}: Readonly<{
  state: WizardState;
  onField: <K extends keyof WizardState["brief"]>(key: K, value: WizardState["brief"][K]) => void;
}>) {
  const b = state.brief;
  return (
    <WizardStep id="wizard-brief-title" title="1 · Project brief">
      <div className="grid gap-3 lg:grid-cols-2">
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wb-title" text="Project title" />
          <input
            id="wb-title"
            aria-label="Project title"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.projectTitle}
            onChange={(e) => onField("projectTitle", e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wb-brand" text="Client or brand" />
          <input
            id="wb-brand"
            aria-label="Client or brand"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.clientOrBrand}
            onChange={(e) => onField("clientOrBrand", e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wb-purpose" text="Project purpose" />
          <input
            id="wb-purpose"
            aria-label="Project purpose"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.projectPurpose}
            onChange={(e) => onField("projectPurpose", e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wb-duration" text="Target duration seconds" />
          <input
            id="wb-duration"
            aria-label="Target duration seconds"
            type="number"
            min={5}
            max={600}
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.targetDurationSeconds}
            onChange={(e) => onField("targetDurationSeconds", Number(e.target.value))}
          />
        </label>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <FieldLabel htmlFor="wb-brief" text="Content brief" />
          <textarea
            id="wb-brief"
            aria-label="Content brief"
            className="min-h-24 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.contentBrief}
            onChange={(e) => onField("contentBrief", e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted lg:col-span-2">
          <FieldLabel htmlFor="wb-notes" text="Operator notes" />
          <textarea
            id="wb-notes"
            aria-label="Operator notes"
            className="min-h-16 w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={b.operatorNotes}
            onChange={(e) => onField("operatorNotes", e.target.value)}
          />
        </label>
      </div>
    </WizardStep>
  );
}
