"use client";

import { WizardStep } from "@/components/wizard/wizard-step";
import { PROJECT_TEMPLATES, type WizardState } from "@/lib/create-project-wizard";

export function StepTemplate({
  state,
  onTemplate,
}: Readonly<{ state: WizardState; onTemplate: (id: string) => void }>) {
  return (
    <WizardStep id="wizard-template-title" title="2 · Template">
      <div className="grid gap-2">
        {PROJECT_TEMPLATES.map((tpl) => (
          <label
            key={tpl.id}
            className="inline-flex min-h-12 items-center gap-3 rounded-lg border border-border-soft bg-surface-2 px-3 py-2 text-xs font-semibold text-ink"
          >
            <input
              aria-label={tpl.label}
              type="radio"
              name="wizard-template"
              checked={state.templateId === tpl.id}
              onChange={() => onTemplate(tpl.id)}
            />
            <span>
              {tpl.label}
              <span className="block text-[11px] font-normal text-ink-muted">{tpl.description}</span>
            </span>
          </label>
        ))}
      </div>
    </WizardStep>
  );
}
