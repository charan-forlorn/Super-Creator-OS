"use client";

import { OUTPUT_PROFILES } from "@/lib/create-project-wizard";
import { WizardStep } from "@/components/wizard/wizard-step";
import type { OutputProfileId } from "@/lib/solo-project-preparation";

export function StepProfiles({
  selected,
  onToggle,
}: Readonly<{ selected: OutputProfileId[]; onToggle: (id: OutputProfileId) => void }>) {
  return (
    <WizardStep id="wizard-profiles-title" title="4 · Output profiles">
      <div className="flex flex-wrap gap-2">
        {OUTPUT_PROFILES.map((profile) => (
          <label
            key={profile.id}
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-border-soft bg-surface-2 px-3 py-2 text-xs font-semibold text-ink"
          >
            <input
              aria-label={profile.label}
              type="checkbox"
              checked={selected.includes(profile.id)}
              onChange={() => onToggle(profile.id)}
            />
            {profile.label} · {profile.aspectRatio}
          </label>
        ))}
      </div>
    </WizardStep>
  );
}
