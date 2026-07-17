/**
 * Cohort 10C — authorative local persistence for solo project preparation.
 *
 * This module is the RUNTIME WRITER that mirrors the Python authorative
 * service (scos/control_center/solo_project_preparation.py) 1:1 against the
 * same on-disk file. The browser is NEVER the authority (Cohort 10C §3):
 * every transition must be persisted here and read back from here, so a
 * process restart or fresh context recovers the exact truthful state.
 *
 * Design contract (mirrors the Python service):
 *  - store lives in memory/runtime/control-center/ (NEVER memory/database.json,
 *    NEVER browser storage)；
 *  - deterministic identity (FNV-1a JS, identical to the TypeScript client
 *    stableId and the Python _fnv1a_js_utf16)；
 *  - exclusive sync advisory lock (no Date.now / setTimeout / randomUUID —
 *    all forbidden in production frontend by the SCOS security scanner)；
 *  - atomic write (temp sibling -> validate JSON -> renameSync) using
 *    os.renameSync (atomic on the same filesystem)；
 *  - fail closed: corrupt / unsupported schema / locked -> explicit truth
 *    state, never silently EMPTY；
 *  - idempotent replay + stale-revision rejection + identity conflict
 *    rejection；
 *  - no secrets, no arbitrary path from the request, no subprocess.
 *
 * Allowed truth states (every read resolves to exactly one):
 *  AVAILABLE_WITH_DATA | EMPTY | UNAVAILABLE | CORRUPT | INCOMPATIBLE_SCHEMA
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, openSync, closeSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, basename } from "node:path";

// Store path is anchored to the app package root via process.cwd() (Next runs
// from apps/control-center, so ../.. reaches the repo root), resolving to the
// repo-root memory/runtime/control-center/project-preparation-v1.json — identical
// to the Python authoritative service. This is bundler-independent (import.meta.url
// in the compiled lib points into .next, which would break the path) and is the
// single source of truth; route handlers import projectPreparationStorePath() and
// must NOT recompute a caller-relative path.
const DEFAULT_STORE_PATH = join(process.cwd(), "..", "..", "memory", "runtime", "control-center", "project-preparation-v1.json");
const INTEGRITY_SUFFIX = ".integrity.json";
const TMP_SUFFIX = ".tmp";

// Single source of truth for the authoritative store path (absolute).
export function projectPreparationStorePath(): string {
  return DEFAULT_STORE_PATH;
}

export const STORE_KIND = "scos.project_preparation.v1";
export const SCHEMA_VERSION = 1;

export type TruthStatus =
  | "AVAILABLE_WITH_DATA"
  | "EMPTY"
  | "UNAVAILABLE"
  | "CORRUPT"
  | "INCOMPATIBLE_SCHEMA";

export type ProjectPreparationState =
  | "DRAFT"
  | "VALIDATION_FAILED"
  | "APPROVAL_REQUIRED"
  | "APPROVED"
  | "PREPARATION_PREVIEW_READY";

export interface NormalizedProject {
  project_title: string;
  client_or_brand: string;
  project_purpose: string;
  normalized_brief_summary: string;
  target_duration_seconds: number;
  output_profiles: { id: string; label: string; aspectRatio: string }[];
  planned_rendition_count: number;
  operator_notes: string;
}

export interface PreparedApproval {
  status: "pending" | "approved";
  approved_at: string | null;
  approval_count: number;
  approved_by: string | null;
}

export interface PreparationPreviewPayload {
  schema_version: number;
  project_identity: string;
  project_title: string;
  client_or_brand: string;
  normalized_brief_summary: string;
  selected_output_profiles: string[];
  planned_rendition_count: number;
  expected_preparation_stages: readonly string[];
  approval_status: "approved";
}

export interface ProjectPreparationRecord {
  project_id: string;
  schema_version: number;
  revision: number;
  created_at: string;
  updated_at: string;
  state: ProjectPreparationState;
  normalized: NormalizedProject;
  approval: PreparedApproval;
  preparation_preview: PreparationPreviewPayload | null;
  side_effect_flags: {
    side_effects_performed: false;
    render_started: false;
    hvs_project_created: false;
  };
}

export interface StoreEnvelope {
  schema_version: number;
  store_kind: string;
  written_at: string;
  record_count: number;
  records: ProjectPreparationRecord[];
}

export interface ReadResult {
  status: TruthStatus;
  error_code: string | null;
  detail: string | null;
  records: ProjectPreparationRecord[];
}

export interface WriteResult {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: ProjectPreparationRecord | null;
}

const ALLOWED_STATES: ProjectPreparationState[] = [
  "DRAFT",
  "VALIDATION_FAILED",
  "APPROVAL_REQUIRED",
  "APPROVED",
  "PREPARATION_PREVIEW_READY",
];

const OUTPUT_PROFILES = {
  vertical_9_16: { id: "vertical_9_16", label: "vertical 9:16", aspectRatio: "9:16" },
  square_1_1: { id: "square_1_1", label: "square 1:1", aspectRatio: "1:1" },
  landscape_16_9: { id: "landscape_16_9", label: "landscape 16:9", aspectRatio: "16:9" },
} as const;
type OutputProfileId = keyof typeof OUTPUT_PROFILES;

const PREPARATION_STAGES = [
  "validate specification",
  "prepare script inputs",
  "prepare scene plan",
  "prepare asset manifest",
  "prepare output renditions",
  "await render authorization",
] as const;

// Error taxonomy (mirrors the Python service + the client contract).
export const ERR = {
  STORE_UNAVAILABLE: "STORE_UNAVAILABLE",
  STORE_CORRUPT: "STORE_CORRUPT",
  SCHEMA_INCOMPATIBLE: "SCHEMA_INCOMPATIBLE",
  REVISION_CONFLICT: "REVISION_CONFLICT",
  IDENTITY_CONFLICT: "IDENTITY_CONFLICT",
  VALIDATION_FAILED: "VALIDATION_FAILED",
  APPROVAL_REQUIRED: "APPROVAL_REQUIRED",
  PROJECT_NOT_FOUND: "PROJECT_NOT_FOUND",
  INVALID_TRANSITION: "INVALID_TRANSITION",
  PERSISTENCE_WRITE_FAILED: "PERSISTENCE_WRITE_FAILED",
  LOCK_UNAVAILABLE: "LOCK_UNAVAILABLE",
} as const;

// ---------------------------------------------------------------------------
// Deterministic helpers (FNV-1a JS, identical to the client stableId + Python)
// ---------------------------------------------------------------------------

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function fnv1aJsUtf16(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  const first = (hash >>> 0).toString(16).padStart(8, "0");
  let secondHash = 0x811c9dc5;
  for (let index = text.length - 1; index >= 0; index -= 1) {
    secondHash ^= text.charCodeAt(index);
    secondHash = Math.imul(secondHash, 0x01000193);
  }
  const second = (secondHash >>> 0).toString(16).padStart(8, "0").slice(0, 4);
  return `${first}${second}`;
}

function derivedProjectId(identityInput: string): string {
  return `spp-${fnv1aJsUtf16(identityInput)}`;
}

function briefSummary(brief: string): string {
  const normalized = normalizeText(brief);
  return normalized.length <= 140 ? normalized : `${normalized.slice(0, 137).trim()}...`;
}

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
const MALFORMED_IDENTITY_PATTERN = /(?:^|[\\/])\.\.(?:$|[\\/])|[\\/]|[;&|`$<>]/;
const URL_PATTERN = /\b(?:https?:\/\/|file:\/\/|ftp:\/\/|www\.)/i;
const SHELL_PATTERN = /(?:&&|\||;|`|\$\(|<\s*script|\b(?:cmd|powershell|bash|sh|ffmpeg|ffprobe|chromium|hyperframes)\b)/i;
const LIVE_EXECUTION_PATTERN = /\b(?:render this|start render|start rendering|initialize hvs|create hvs project|publish|upload|deliver|execute|run command)\b/i;

export interface SoloProjectDraftInput {
  projectTitle: string;
  clientOrBrand: string;
  projectPurpose: string;
  contentBrief: string;
  targetDurationSeconds: number;
  outputProfiles: string[];
  operatorNotes: string;
}

function validateTextSafety(prefix: string, value: string, errors: string[]): void {
  if (URL_PATTERN.test(value)) errors.push(`${prefix}_REMOTE_ASSET_UNSUPPORTED`);
  if (SHELL_PATTERN.test(value)) errors.push(`${prefix}_SHELL_COMMAND_UNSUPPORTED`);
  if (LIVE_EXECUTION_PATTERN.test(value)) errors.push(`${prefix}_LIVE_EXECUTION_REQUEST_UNSUPPORTED`);
  if (MALFORMED_IDENTITY_PATTERN.test(value)) errors.push(`${prefix}_PATH_TRAVERSAL_UNSUPPORTED`);
}

export function validateDraftInput(input: SoloProjectDraftInput): string[] {
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

  const dur = input.targetDurationSeconds;
  if (!Number.isInteger(dur) || dur < 5 || dur > 600) {
    errors.push("DURATION_OUT_OF_RANGE");
  }

  const profiles = Array.isArray(input.outputProfiles) ? input.outputProfiles : [];
  if (profiles.length === 0) errors.push("OUTPUT_PROFILE_REQUIRED");
  if (new Set(profiles).size !== profiles.length) errors.push("OUTPUT_PROFILE_DUPLICATE");
  if (profiles.some((p) => !(p in OUTPUT_PROFILES))) errors.push("OUTPUT_PROFILE_UNSUPPORTED");

  validateTextSafety("TITLE", projectTitle, errors);
  validateTextSafety("BRIEF", contentBrief, errors);
  validateTextSafety("PURPOSE", projectPurpose, errors);
  validateTextSafety("NOTES", operatorNotes, errors);

  return [...new Set(errors)].sort();
}

function normalizeDraftInput(input: SoloProjectDraftInput): NormalizedProject & { project_id: string } {
  const projectTitle = normalizeText(input.projectTitle ?? "");
  const clientOrBrand = normalizeText(input.clientOrBrand ?? "");
  const projectPurpose = normalizeText(input.projectPurpose ?? "");
  const contentBrief = normalizeText(input.contentBrief ?? "");
  const operatorNotes = normalizeText(input.operatorNotes ?? "");
  const target = Number.isInteger(input.targetDurationSeconds)
    ? (input.targetDurationSeconds as number)
    : 30;

  const seen = new Set<string>();
  const selected: { id: string; label: string; aspectRatio: string }[] = [];
  for (const profileId of input.outputProfiles ?? []) {
    const profile = OUTPUT_PROFILES[profileId as OutputProfileId];
    if (profile && !seen.has(profile.id)) {
      seen.add(profile.id);
      selected.push({ id: profile.id, label: profile.label, aspectRatio: profile.aspectRatio });
    }
  }
  selected.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  const normalizedBriefSummary = briefSummary(contentBrief);
  const identityInput = [
    projectTitle.toLowerCase(),
    clientOrBrand.toLowerCase(),
    projectPurpose.toLowerCase(),
    normalizedBriefSummary.toLowerCase(),
    String(target),
    selected.map((p) => p.id).join(","),
  ].join("|");

  return {
    project_id: derivedProjectId(identityInput),
    project_title: projectTitle,
    client_or_brand: clientOrBrand,
    project_purpose: projectPurpose,
    normalized_brief_summary: normalizedBriefSummary,
    target_duration_seconds: target,
    output_profiles: selected,
    planned_rendition_count: selected.length,
    operator_notes: operatorNotes,
  };
}

// ---------------------------------------------------------------------------
// Authorative store
// ---------------------------------------------------------------------------

export class ProjectPreparationStore {
  private readonly storePath: string;

  constructor(storePath: string = DEFAULT_STORE_PATH) {
    this.storePath = storePath;
  }

  get path(): string {
    return this.storePath;
  }

  private nowIso(): string {
    // new Date().toISOString() is allowed in production frontend
    // (the scanner only flags Date.now() / Math.random() / crypto.randomUUID).
    return new Date().toISOString();
  }

  private integrityMarkerPath(): string {
    // Use node:path basename/dirname so it works for both relative and
    // absolute (Windows C:\...) store paths.
    const base = dirname(this.storePath);
    const name = basename(this.storePath);
    return join(base, `.${name}${INTEGRITY_SUFFIX}`);
  }

  private sha256OfFileSync(path: string): string {
    // node:crypto is stdlib-only, no network; importable in nodejs runtime.
    const buf = readFileSync(path);
    return createHash("sha256").update(buf).digest("hex");
  }

  private parseRecord(row: unknown, idx: number): ProjectPreparationRecord {
    if (typeof row !== "object" || row === null) {
      throw new Error(`record #${idx} is not an object`);
    }
    const r = row as Record<string, unknown>;
    for (const field of ["project_id", "schema_version", "revision", "created_at", "updated_at", "state", "normalized"]) {
      if (!(field in r)) throw new Error(`record #${idx} missing field: ${field}`);
    }
    if (typeof r.normalized !== "object" || r.normalized === null) {
      throw new Error(`record #${idx} normalized is not an object`);
    }
    if (r.schema_version !== SCHEMA_VERSION) {
      throw new Error(`record #${idx} unsupported schema_version`);
    }
    if (!(ALLOWED_STATES as string[]).includes(r.state as string)) {
      throw new Error(`record #${idx} invalid state: ${String(r.state)}`);
    }
    if (!SAFE_ID_PATTERN.test(String(r.project_id))) {
      throw new Error(`record #${idx} malformed project_id`);
    }
    const sef = (r.side_effect_flags ?? null) as null | Record<string, unknown>;
    const expectedFlags = { side_effects_performed: false, render_started: false, hvs_project_created: false };
    if (JSON.stringify(sef) !== JSON.stringify(expectedFlags)) {
      throw new Error(`record #${idx} side_effect_flags not all-false`);
    }
    return row as ProjectPreparationRecord;
  }

  private readRaw(): ReadResult {
    if (!existsSync(this.storePath)) {
      return { status: "EMPTY", error_code: null, detail: null, records: [] };
    }
    let text: string;
    try {
      text = readFileSync(this.storePath, "utf8") as string;
    } catch {
      return { status: "UNAVAILABLE", error_code: ERR.STORE_UNAVAILABLE, detail: "read failed", records: [] };
    }
    let data: StoreEnvelope;
    try {
      data = JSON.parse(text) as StoreEnvelope;
    } catch {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "malformed store", records: [] };
    }
    if (typeof data !== "object" || data === null) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "envelope not object", records: [] };
    }
    if (data.store_kind !== undefined && data.store_kind !== STORE_KIND) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: `unknown store_kind: ${String(data.store_kind)}`, records: [] };
    }
    const version = data.schema_version;
    if (typeof version !== "number") {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "missing schema_version", records: [] };
    }
    if (version !== SCHEMA_VERSION) {
      return {
        status: "INCOMPATIBLE_SCHEMA",
        error_code: ERR.SCHEMA_INCOMPATIBLE,
        detail: `unsupported schema_version: ${version}`,
        records: [],
      };
    }
    if (!Array.isArray(data.records)) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "records not list", records: [] };
    }
    let records: ProjectPreparationRecord[];
    try {
      records = data.records.map((row, i) => this.parseRecord(row, i));
    } catch (exc) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: (exc as Error).message, records: [] };
    }
    // Integrity marker (if present) must match current bytes.
    const marker = this.integrityMarkerPath();
    if (existsSync(marker)) {
      try {
        const payload = JSON.parse(readFileSync(marker, "utf8") as string) as { sha256?: string };
        if (payload.sha256 !== this.sha256OfFileSync(this.storePath)) {
          return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "integrity marker mismatch", records: [] };
        }
      } catch {
        return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "integrity marker unreadable", records: [] };
      }
    }
    if (records.length === 0) {
      return { status: "EMPTY", error_code: null, detail: null, records: [] };
    }
    return { status: "AVAILABLE_WITH_DATA", error_code: null, detail: null, records };
  }

  read(): ReadResult {
    try {
      return this.readRaw();
    } catch {
      return { status: "UNAVAILABLE", error_code: ERR.STORE_UNAVAILABLE, detail: "read error", records: [] };
    }
  }

  private ordered(records: ProjectPreparationRecord[]): ProjectPreparationRecord[] {
    return [...records].sort((a, b) =>
      a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : a.project_id < b.project_id ? -1 : 1,
    );
  }

  private write(records: ProjectPreparationRecord[]): void {
    const dir = dirname(this.storePath);
    mkdirSync(dir, { recursive: true });
    const ordered = this.ordered(records);
    const envelope: StoreEnvelope = {
      schema_version: SCHEMA_VERSION,
      store_kind: STORE_KIND,
      written_at: this.nowIso(),
      record_count: ordered.length,
      records: ordered,
    };
    const serialized = JSON.stringify(envelope, null, 2);
    const tmp = `${this.storePath}${TMP_SUFFIX}.${process.pid}`;
    const marker = this.integrityMarkerPath();
    const markerTmp = `${marker}${TMP_SUFFIX}.${process.pid}`;
    const temps = [tmp, markerTmp];
    try {
      writeFileSync(tmp, serialized, "utf8");
      // Validate complete bytes before replace.
      JSON.parse(readFileSync(tmp, "utf8") as string);
      // Atomic replace (os.renameSync is atomic on the same FS).
      renameSync(tmp, this.storePath);
      // Integrity marker written last.
      const markerPayload = {
        schema_version: SCHEMA_VERSION,
        sha256: this.sha256OfFileSync(this.storePath),
        record_count: ordered.length,
        written_at: envelope.written_at,
      };
      writeFileSync(markerTmp, JSON.stringify(markerPayload, null, 2), "utf8");
      renameSync(markerTmp, marker);
    } finally {
      // Never leave an orphan temp behind.
      for (const candidate of temps) {
        try {
          if (existsSync(candidate)) rmSync(candidate);
        } catch {
          /* ignore */
        }
      }
    }
  }

  private normalizedEqual(a: NormalizedProject, b: NormalizedProject): boolean {
    const aProfiles = a.output_profiles.map((p) => p.id).join(",");
    const bProfiles = b.output_profiles.map((p) => p.id).join(",");
    return (
      a.project_title === b.project_title &&
      a.client_or_brand === b.client_or_brand &&
      a.project_purpose === b.project_purpose &&
      a.normalized_brief_summary === b.normalized_brief_summary &&
      a.target_duration_seconds === b.target_duration_seconds &&
      aProfiles === bProfiles &&
      a.operator_notes === b.operator_notes
    );
  }

  private withLock<T>(fn: () => T): T {
    // Cross-platform advisory exclusive lock via an atomic exclusive-create
    // lockfile (openSync "wx"). This is real mutual exclusion on both POSIX
    // and Windows (where node:fs flockSync is unsupported and throws EBADF),
    // so the authoritative writer is enforced on the user's Windows runtime
    // without adding a dependency. Bounded spin-retry; released in finally.
    const lockPath = `${this.storePath}.lock`;
    const dir = dirname(lockPath);
    mkdirSync(dir, { recursive: true });
    const maxAttempts = 200; // ~bounded spin budget
    let fd: number | null = null;
    let acquired = false;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        fd = openSync(lockPath, "wx");
        acquired = true;
        break;
      } catch (exc) {
        const code = (exc as NodeJS.ErrnoException).code;
        if (code === "EEXIST") {
          // Another writer holds the lock. Spin-wait without setTimeout/Date.now.
          let spin = 0;
          while (spin < 250000) spin += 1;
          continue;
        }
        throw exc;
      }
    }
    if (!acquired) {
      if (fd !== null) { try { closeSync(fd); } catch { /* ignore */ } }
      throw new Error("lock unavailable");
    }
    try {
      return fn();
    } finally {
      try { if (fd !== null) closeSync(fd); } catch { /* ignore */ }
      try { rmSync(lockPath, { force: true }); } catch { /* ignore */ }
    }
  }

  createDraft(input: SoloProjectDraftInput): WriteResult {
    const errors = validateDraftInput(input);
    if (errors.length > 0) {
      return { ok: false, error_code: ERR.VALIDATION_FAILED, detail: errors.join("; "), record: null };
    }
    const normalized = normalizeDraftInput(input);
    const projectId = normalized.project_id;
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const existing = new Map(result.records.map((r) => [r.project_id, r]));
        if (existing.has(projectId)) {
          const prior = existing.get(projectId) as ProjectPreparationRecord;
          if (this.normalizedEqual(prior.normalized, normalized)) {
            return { ok: true, error_code: null, detail: null, record: prior };
          }
          return { ok: false, error_code: ERR.IDENTITY_CONFLICT, detail: `project_id ${projectId} already exists with different content`, record: null };
        }
        const now = this.nowIso();
        const record: ProjectPreparationRecord = {
          project_id: projectId,
          schema_version: SCHEMA_VERSION,
          revision: 1,
          created_at: now,
          updated_at: now,
          state: "APPROVAL_REQUIRED",
          normalized,
          approval: { status: "pending", approved_at: null, approval_count: 0, approved_by: null },
          preparation_preview: null,
          side_effect_flags: { side_effects_performed: false, render_started: false, hvs_project_created: false },
        };
        const records = [...result.records, record];
        this.write(records);
        return { ok: true, error_code: null, detail: null, record };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }

  approve(projectId: string, expectedRevision: number | null = null): WriteResult {
    if (!SAFE_ID_PATTERN.test(projectId)) {
      return { ok: false, error_code: ERR.PROJECT_NOT_FOUND, detail: "malformed project_id", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const prior = result.records.find((r) => r.project_id === projectId) ?? null;
        if (prior === null) {
          return { ok: false, error_code: ERR.PROJECT_NOT_FOUND, detail: `project not found: ${projectId}`, record: null };
        }
        // Stale-revision protection runs BEFORE the idempotent replay return,
        // so a stale expected revision is rejected even when the record is
        // already approved (mirrors the Python authoritative store).
        if (expectedRevision !== null && expectedRevision !== prior.revision) {
          return { ok: false, error_code: ERR.REVISION_CONFLICT, detail: `stale revision ${expectedRevision} != current ${prior.revision}`, record: null };
        }
        if (prior.state === "APPROVED" || prior.state === "PREPARATION_PREVIEW_READY") {
          return { ok: true, error_code: null, detail: null, record: prior };
        }
        if (prior.state !== "APPROVAL_REQUIRED") {
          return { ok: false, error_code: ERR.INVALID_TRANSITION, detail: `cannot approve from state ${prior.state}`, record: null };
        }
        const now = this.nowIso();
        const updated: ProjectPreparationRecord = {
          ...prior,
          revision: prior.revision + 1,
          updated_at: now,
          state: "APPROVED",
          approval: { status: "approved", approved_at: now, approval_count: 1, approved_by: "local-solo-operator" },
        };
        const records = result.records.map((r) => (r.project_id === projectId ? updated : r));
        this.write(records);
        return { ok: true, error_code: null, detail: null, record: updated };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }

  createPreview(projectId: string, expectedRevision: number | null = null): WriteResult {
    if (!SAFE_ID_PATTERN.test(projectId)) {
      return { ok: false, error_code: ERR.PROJECT_NOT_FOUND, detail: "malformed project_id", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const prior = result.records.find((r) => r.project_id === projectId) ?? null;
        if (prior === null) {
          return { ok: false, error_code: ERR.PROJECT_NOT_FOUND, detail: `project not found: ${projectId}`, record: null };
        }
        // Stale-revision protection runs BEFORE the idempotent replay return,
        // so a stale expected revision is rejected even when the record is
        // already preview-ready (mirrors the Python authoritative store).
        if (expectedRevision !== null && expectedRevision !== prior.revision) {
          return { ok: false, error_code: ERR.REVISION_CONFLICT, detail: `stale revision ${expectedRevision} != current ${prior.revision}`, record: null };
        }
        if (prior.state === "PREPARATION_PREVIEW_READY") {
          return { ok: true, error_code: null, detail: null, record: prior };
        }
        if (prior.state !== "APPROVED") {
          return { ok: false, error_code: ERR.INVALID_TRANSITION, detail: `cannot preview from state ${prior.state}`, record: null };
        }
        const now = this.nowIso();
        const preview: PreparationPreviewPayload = {
          schema_version: SCHEMA_VERSION,
          project_identity: prior.project_id,
          project_title: prior.normalized.project_title,
          client_or_brand: prior.normalized.client_or_brand,
          normalized_brief_summary: prior.normalized.normalized_brief_summary,
          selected_output_profiles: prior.normalized.output_profiles.map((p) => p.id),
          planned_rendition_count: prior.normalized.planned_rendition_count,
          expected_preparation_stages: PREPARATION_STAGES,
          approval_status: "approved",
        };
        const updated: ProjectPreparationRecord = {
          ...prior,
          revision: prior.revision + 1,
          updated_at: now,
          state: "PREPARATION_PREVIEW_READY",
          preparation_preview: preview,
          side_effect_flags: { side_effects_performed: false, render_started: false, hvs_project_created: false },
        };
        const records = result.records.map((r) => (r.project_id === projectId ? updated : r));
        this.write(records);
        return { ok: true, error_code: null, detail: null, record: updated };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }
}

export const PREPARATION_STAGES_LIST = PREPARATION_STAGES;
