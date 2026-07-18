"use client";

import { WizardStep, FieldLabel } from "@/components/wizard/wizard-step";
import type { WizardState } from "@/lib/create-project-wizard";

export function StepAssets({
  state,
  onAssetRef,
  onBrandKit,
}: Readonly<{
  state: WizardState;
  onAssetRef: (value: string) => void;
  onBrandKit: (value: string) => void;
}>) {
  return (
    <WizardStep id="wizard-assets-title" title="3 · Assets & brand">
      <p className="text-xs text-ink-muted">
        Asset staging and brand kit are referenced by server-resolved identifiers. The browser
        never supplies a filesystem path.
      </p>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wa-asset" text="Asset staging reference" />
          <input
            id="wa-asset"
            aria-label="Asset staging reference"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={state.assetRef}
            placeholder="e.g. assets/promo-001"
            onChange={(e) => onAssetRef(e.target.value)}
          />
        </label>
        <label className="block text-xs text-ink-muted">
          <FieldLabel htmlFor="wa-brand" text="Brand kit id (optional)" />
          <input
            id="wa-brand"
            aria-label="Brand kit id"
            className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-ink"
            value={state.brandKitId}
            placeholder="e.g. bkb-xxxxxxxxxxxx"
            onChange={(e) => onBrandKit(e.target.value)}
          />
        </label>
      </div>
    </WizardStep>
  );
}
