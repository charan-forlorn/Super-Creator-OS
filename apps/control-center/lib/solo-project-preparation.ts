export const SOLO_PROJECT_PREPARATION_SCHEMA_VERSION = "scos.solo-project-preparation.v1";
export const ACTUAL_DURABILITY_CLASS = "RUNTIME_MEMORY_ONLY";

export const OUTPUT_PROFILES = [
  { id: "vertical_9_16", label: "vertical 9:16", aspectRatio: "9:16" },
  { id: "square_1_1", label: "square 1:1", aspectRatio: "1:1" },
  { id: "landscape_16_9", label: "landscape 16:9", aspectRatio: "16:9" },
] as const;

export const PREPARATION_STAGES = [
  "validate specification",
  "prepare script inputs",
  "prepare scene plan",
  "prepare asset manifest",
  "prepare output renditions",
  "await render authorization",
] as const;

export type OutputProfileId = (typeof OUTPUT_PROFILES)[number]["id"];

export type ProjectPreparationState =
  | "DRAFT"
  | "VALIDATION_FAILED"
  | "APPROVAL_REQUIRED"
  | "APPROVED"
  | "PREPARATION_PREVIEW_READY";

export interface SoloProjectDraftInput {
  projectTitle: string;
  clientOrBrand: string;
  projectPurpose: string;
  contentBrief: string;
  targetDurationSeconds: number;
  outputProfiles: OutputProfileId[];
  operatorNotes: string;
}

export interface NormalizedOutputProfile {
  id: OutputProfileId;
  label: string;
  aspectRatio: string;
}

export interface PreparedProjectDraft {
  projectIdentity: string;
  projectTitle: string;
  clientOrBrand: string;
  projectPurpose: string;
  normalizedBriefSummary: string;
  targetDurationSeconds: number;
  outputProfiles: NormalizedOutputProfile[];
  plannedRenditionCount: number;
  operatorNotes: string;
}

export interface PreparationPreview {
  schema_version: typeof SOLO_PROJECT_PREPARATION_SCHEMA_VERSION;
  project_identity: string;
  project_title: string;
  client_or_brand: string;
  normalized_brief_summary: string;
  selected_output_profiles: OutputProfileId[];
  planned_rendition_count: number;
  expected_preparation_stages: readonly string[];
  approval_status: "approved";
  side_effects_performed: false;
  render_started: false;
  hvs_project_created: false;
}

export interface PreparationWorkflowProjection {
  ok: boolean;
  state: ProjectPreparationState;
  durabilityClass: typeof ACTUAL_DURABILITY_CLASS;
  project: PreparedProjectDraft | null;
  approvalProjectIdentity: string | null;
  approvalCount: number;
  previewCount: number;
  preview: PreparationPreview | null;
  errors: string[];
}

const PROFILE_BY_ID = new Map(OUTPUT_PROFILES.map((profile) => [profile.id, profile]));
const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
const MALFORMED_IDENTITY_PATTERN = /(^|[\\/])\.\.($|[\\/])|[\\/]|[;&|`$<>]/;
const URL_PATTERN = /\b(?:https?:\/\/|file:\/\/|ftp:\/\/|www\.)/i;
const SHELL_PATTERN = /(?:&&|\|\||;|`|\$\(|<\s*script|\b(?:cmd|powershell|bash|sh|ffmpeg|ffprobe|chromium|hyperframes)\b)/i;
const LIVE_EXECUTION_PATTERN = /\b(?:render this|start render|start rendering|initialize hvs|create hvs project|publish|upload|deliver|execute|run command)\b/i;

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function stableId(prefix: string, text: string): string {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  const first = (hash >>> 0).toString(16).padStart(8, "0");
  let secondHash = 2166136261;
  for (let index = text.length - 1; index >= 0; index -= 1) {
    secondHash ^= text.charCodeAt(index);
    secondHash = Math.imul(secondHash, 16777619);
  }
  const second = (secondHash >>> 0).toString(16).padStart(8, "0").slice(0, 4);
  return `${prefix}${first}${second}`;
}

function briefSummary(brief: string): string {
  const normalized = normalizeText(brief);
  return normalized.length <= 140 ? normalized : `${normalized.slice(0, 137).trim()}...`;
}

function validateTextSafety(prefix: string, value: string, errors: string[]) {
  if (URL_PATTERN.test(value)) errors.push(`${prefix}_REMOTE_ASSET_UNSUPPORTED`);
  if (SHELL_PATTERN.test(value)) errors.push(`${prefix}_SHELL_COMMAND_UNSUPPORTED`);
  if (LIVE_EXECUTION_PATTERN.test(value)) errors.push(`${prefix}_LIVE_EXECUTION_REQUEST_UNSUPPORTED`);
  if (MALFORMED_IDENTITY_PATTERN.test(value)) errors.push(`${prefix}_PATH_TRAVERSAL_UNSUPPORTED`);
}

export function validateProjectDraft(input: SoloProjectDraftInput): string[] {
  const errors: string[] = [];
  const projectTitle = normalizeText(input.projectTitle ?? "");
  const clientOrBrand = normalizeText(input.clientOrBrand ?? "");
  const projectPurpose = normalizeText(input.projectPurpose ?? "");
  const contentBrief = normalizeText(input.contentBrief ?? "");
  const operatorNotes = normalizeText(input.operatorNotes ?? "");

  if (!projectTitle) errors.push("PROJECT_TITLE_REQUIRED");
  if (!contentBrief) errors.push("BRIEF_REQUIRED");
  if (!clientOrBrand) errors.push("CLIENT_OR_BRAND_REQUIRED");
  if (!projectPurpose) errors.push("PROJECT_PURPOSE_REQUIRED");
  if (projectTitle && MALFORMED_IDENTITY_PATTERN.test(projectTitle)) errors.push("PROJECT_TITLE_MALFORMED");
  if (!Number.isInteger(input.targetDurationSeconds) || input.targetDurationSeconds < 5 || input.targetDurationSeconds > 600) {
    errors.push("DURATION_OUT_OF_RANGE");
  }

  const profiles = input.outputProfiles ?? [];
  if (profiles.length === 0) errors.push("OUTPUT_PROFILE_REQUIRED");
  if (new Set(profiles).size !== profiles.length) errors.push("OUTPUT_PROFILE_DUPLICATE");
  if (profiles.some((profile) => !PROFILE_BY_ID.has(profile))) errors.push("OUTPUT_PROFILE_UNSUPPORTED");

  validateTextSafety("TITLE", projectTitle, errors);
  validateTextSafety("BRIEF", contentBrief, errors);
  validateTextSafety("PURPOSE", projectPurpose, errors);
  validateTextSafety("NOTES", operatorNotes, errors);

  return [...new Set(errors)].sort();
}

export function prepareProjectDraft(input: SoloProjectDraftInput): PreparationWorkflowProjection {
  const errors = validateProjectDraft(input);
  if (errors.length > 0) {
    return {
      ok: false,
      state: "VALIDATION_FAILED",
      durabilityClass: ACTUAL_DURABILITY_CLASS,
      project: null,
      approvalProjectIdentity: null,
      approvalCount: 0,
      previewCount: 0,
      preview: null,
      errors,
    };
  }

  const selectedProfiles = [...new Set(input.outputProfiles)].map((profileId) => {
    const profile = PROFILE_BY_ID.get(profileId);
    if (!profile) throw new Error(`Unsupported output profile reached normalization: ${profileId}`);
    return { id: profile.id, label: profile.label, aspectRatio: profile.aspectRatio };
  });
  const projectTitle = normalizeText(input.projectTitle);
  const clientOrBrand = normalizeText(input.clientOrBrand);
  const projectPurpose = normalizeText(input.projectPurpose);
  const normalizedBriefSummary = briefSummary(input.contentBrief);
  const identityInput = [
    projectTitle.toLowerCase(),
    clientOrBrand.toLowerCase(),
    projectPurpose.toLowerCase(),
    normalizedBriefSummary.toLowerCase(),
    String(input.targetDurationSeconds),
    selectedProfiles.map((profile) => profile.id).join(","),
  ].join("|");

  return {
    ok: true,
    state: "APPROVAL_REQUIRED",
    durabilityClass: ACTUAL_DURABILITY_CLASS,
    project: {
      projectIdentity: stableId("spp-", identityInput),
      projectTitle,
      clientOrBrand,
      projectPurpose,
      normalizedBriefSummary,
      targetDurationSeconds: input.targetDurationSeconds,
      outputProfiles: selectedProfiles,
      plannedRenditionCount: selectedProfiles.length,
      operatorNotes: normalizeText(input.operatorNotes),
    },
    approvalProjectIdentity: null,
    approvalCount: 0,
    previewCount: 0,
    preview: null,
    errors: [],
  };
}

function validateIdentity(value: string): string | null {
  return SAFE_ID_PATTERN.test(value) ? null : "MALFORMED";
}

export function approvePreparationRequest(
  projection: PreparationWorkflowProjection,
  projectIdentity: string,
): PreparationWorkflowProjection {
  if (!projection.project || projection.state === "VALIDATION_FAILED") {
    return { ...projection, errors: ["APPROVAL_REQUIRES_VALIDATED_DRAFT"] };
  }
  if (validateIdentity(projectIdentity)) {
    return { ...projection, errors: ["APPROVAL_PROJECT_ID_MALFORMED"] };
  }
  if (projectIdentity !== projection.project.projectIdentity) {
    return { ...projection, errors: ["APPROVAL_PROJECT_ID_MISMATCH"] };
  }
  if (projection.state === "APPROVED" || projection.state === "PREPARATION_PREVIEW_READY") {
    return { ...projection, errors: [] };
  }
  if (projection.state !== "APPROVAL_REQUIRED") {
    return { ...projection, errors: ["APPROVAL_REQUIRES_APPROVAL_REQUIRED_STATE"] };
  }
  return {
    ...projection,
    ok: true,
    state: "APPROVED",
    approvalProjectIdentity: projectIdentity,
    approvalCount: 1,
    errors: [],
  };
}

export function generatePreparationPreview(
  projection: PreparationWorkflowProjection,
  projectIdentity: string,
): PreparationWorkflowProjection {
  if (!projection.project) {
    return { ...projection, errors: ["PREVIEW_REQUIRES_VALIDATED_DRAFT"] };
  }
  if (validateIdentity(projectIdentity)) {
    return { ...projection, errors: ["PREVIEW_PROJECT_ID_MALFORMED"] };
  }
  if (projectIdentity !== projection.project.projectIdentity) {
    return { ...projection, errors: ["PREVIEW_PROJECT_ID_MISMATCH"] };
  }
  if (projection.state === "PREPARATION_PREVIEW_READY") {
    return { ...projection, errors: [] };
  }
  if (projection.state !== "APPROVED") {
    return { ...projection, errors: ["PREVIEW_REQUIRES_APPROVAL"] };
  }

  return {
    ...projection,
    state: "PREPARATION_PREVIEW_READY",
    previewCount: 1,
    preview: {
      schema_version: SOLO_PROJECT_PREPARATION_SCHEMA_VERSION,
      project_identity: projection.project.projectIdentity,
      project_title: projection.project.projectTitle,
      client_or_brand: projection.project.clientOrBrand,
      normalized_brief_summary: projection.project.normalizedBriefSummary,
      selected_output_profiles: projection.project.outputProfiles.map((profile) => profile.id),
      planned_rendition_count: projection.project.plannedRenditionCount,
      expected_preparation_stages: PREPARATION_STAGES,
      approval_status: "approved",
      side_effects_performed: false,
      render_started: false,
      hvs_project_created: false,
    },
    errors: [],
  };
}
