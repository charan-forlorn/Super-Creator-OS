/**
 * Phase 2 — Create Project Wizard state machine + per-step validation.
 *
 * Composes validateProjectDraft (lib/solo-project-preparation) for the
 * Brief step, and gates the remaining steps on prior validity. Paths are
 * server-resolved; the wizard only ever sends profile ids, never filesystem
 * paths (mirrors the project-preparation contract).
 */

import {
  OUTPUT_PROFILES,
  validateProjectDraft,
  type OutputProfileId,
  type SoloProjectDraftInput,
} from "@/lib/solo-project-preparation";

export const WIZARD_STEPS = [
  "brief",
  "template",
  "assets",
  "profiles",
  "confirm",
] as const;

export type WizardStep = (typeof WIZARD_STEPS)[number];

export interface WizardState {
  step: WizardStep;
  brief: SoloProjectDraftInput;
  templateId: string;
  assetRef: string;
  brandKitId: string;
}

export const INITIAL_WIZARD_STATE: WizardState = {
  step: "brief",
  brief: {
    projectTitle: "",
    clientOrBrand: "",
    projectPurpose: "",
    contentBrief: "",
    targetDurationSeconds: 30,
    outputProfiles: ["vertical_9_16"],
    operatorNotes: "",
  },
  templateId: "standard-promo",
  assetRef: "",
  brandKitId: "",
};

export const PROJECT_TEMPLATES = [
  { id: "standard-promo", label: "Standard promo", description: "Single-message vertical promo" },
  { id: "explainer", label: "Explainer", description: "Step-by-step explainer" },
  { id: "social-pack", label: "Social pack", description: "Multi-aspect social cutdown" },
] as const;

export function validateBrief(state: WizardState): string[] {
  return validateProjectDraft(state.brief);
}

export function validateAssets(state: WizardState): string[] {
  const errors: string[] = [];
  if (state.assetRef && /[;&|`$<>]/.test(state.assetRef)) {
    errors.push("ASSET_REF_MALFORMED");
  }
  return errors;
}

export function canAdvance(state: WizardState): boolean {
  switch (state.step) {
    case "brief":
      return validateBrief(state).length === 0;
    case "template":
      return PROJECT_TEMPLATES.some((t) => t.id === state.templateId);
    case "assets":
      return validateAssets(state).length === 0;
    case "profiles":
      return state.brief.outputProfiles.length > 0;
    case "confirm":
      return true;
    default:
      return false;
  }
}

export function stepIndex(step: WizardStep): number {
  return WIZARD_STEPS.indexOf(step);
}

export { OUTPUT_PROFILES, type OutputProfileId };
