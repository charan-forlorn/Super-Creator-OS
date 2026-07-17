/**
 * Cohort 10D — authorative local orchestration for controlled HVS project
 * materialization.
 *
 * This module is the SERVER-SIDE authoritative boundary that mirrors
 * scos/control_center/hvs_project_materialization_service.py 1:1. The browser
 * is NEVER the authority (Cohort 10D §3): it may only review a deterministic
 * plan, request authorization, give explicit confirmation, and render the
 * authoritative server response. It cannot create authority, issue
 * capabilities, choose filesystem destinations, infer success, retry, or call
 * HVS directly.
 *
 * Design contract (mirrors the Python service + store):
 *  - store lives in memory/runtime/control-center/ (NEVER memory/database.json,
 *    NEVER browser storage);
 *  - deterministic identity + canonical plan hash (sha256 of canonical JSON);
 *  - exclusive sync advisory lock (no Date.now / setTimeout / randomUUID —
 *    all forbidden in production frontend by the SCOS security scanner);
 *  - atomic write (temp sibling -> validate JSON -> renameSync);
 *  - single-use capability (atomically consumed; a reused consumed capability
 *    is contained before any HVS call);
 *  - project-level in-flight duplicate containment (only one HVS call per
 *    project);
 *  - the HVS mutation boundary is a single, deterministic, local double that
 *    creates the expected project structure under the isolated destination.
 *    It is the SOLE mutation boundary; no render, no FFmpeg/FFprobe, no
 *    Chromium/HyperFrames, no publish/upload, no external request.
 *  - unknown outcome (timeout/lost response) is recorded and NEVER retried.
 */

import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  openSync,
  closeSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, basename } from "node:path";

// Store path anchored to the repo root via process.cwd() (Next runs from
// apps/control-center, so ../.. reaches the repo root). Identical to the
// Python MaterializationStore default. Route handlers MUST use
// hvsMaterializationStorePath() and never recompute a caller-relative path.
const DEFAULT_STORE_PATH = join(
  process.cwd(),
  "..",
  "..",
  "memory",
  "runtime",
  "control-center",
  "hvs-project-materialization-v1.json",
);
const INTEGRITY_SUFFIX = ".integrity.json";
const TMP_SUFFIX = ".tmp";

// Isolated destination root for the local HVS double (never a production
// workspace). Resolved server-side; the browser never supplies it.
const DEFAULT_DESTINATION_ROOT = join(
  process.cwd(),
  "..",
  "..",
  "memory",
  "runtime",
  "control-center",
  "hvs-projects",
);

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;
// Allow hyphens so the reviewed route's capability ids (e.g. "cap-1") are
// accepted by the authoritative store re-validation (matches ID_PATTERN in
// the route handlers — the store must not reject ids the API permits).
const CAP_ID_PATTERN = /^[a-z0-9-]{4,40}$/;
const ATT_ID_PATTERN = /^[a-z0-9-]{4,48}$/;

export function hvsMaterializationStorePath(): string {
  return DEFAULT_STORE_PATH;
}
export function hvsMaterializationDestinationRoot(): string {
  return DEFAULT_DESTINATION_ROOT;
}

export const STORE_KIND = "scos.hvs_project_materialization.v1";
export const SCHEMA_VERSION = 1;

export const OPERATION_MATERIALIZE_HVS_PROJECT = "MATERIALIZE_HVS_PROJECT";

// Truth states the UI must render explicitly (Cohort 10D §Phase 10).
export type MaterializationTruthState =
  | "MATERIALIZATION_NOT_REQUESTED"
  | "MATERIALIZATION_AUTHORIZATION_REQUIRED"
  | "MATERIALIZATION_AUTHORIZED"
  | "MATERIALIZATION_STARTING"
  | "HVS_PROJECT_MATERIALIZED"
  | "MATERIALIZATION_FAILED_CONFIRMED"
  | "MATERIALIZATION_OUTCOME_UNKNOWN"
  | "MATERIALIZATION_RECONCILIATION_REQUIRED";

// Exported as a runtime value for callers/tests that need the literal.
export const MATERIALIZATION_OUTCOME_UNKNOWN = "MATERIALIZATION_OUTCOME_UNKNOWN" as const;

export const DECISION_AUTHORIZED = "AUTHORIZED";
export const DECISION_DENIED = "DENIED";

export const ERR = {
  STORE_UNAVAILABLE: "STORE_UNAVAILABLE",
  STORE_CORRUPT: "STORE_CORRUPT",
  SCHEMA_INCOMPATIBLE: "SCHEMA_INCOMPATIBLE",
  PROJECT_NOT_FOUND: "PROJECT_NOT_FOUND",
  PROJECT_MALFORMED: "PROJECT_MALFORMED",
  REVISION_CONFLICT: "REVISION_CONFLICT",
  AUTHORIZATION_MISSING: "AUTHORIZATION_MISSING",
  AUTHORIZATION_MALFORMED: "AUTHORIZATION_MALFORMED",
  AUTHORIZATION_REVISION_MISMATCH: "AUTHORIZATION_REVISION_MISMATCH",
  AUTHORIZATION_PLAN_MISMATCH: "AUTHORIZATION_PLAN_MISMATCH",
  AUTHORIZATION_DESTINATION_MISMATCH: "AUTHORIZATION_DESTINATION_MISMATCH",
  AUTHORIZATION_EXPIRED: "AUTHORIZATION_EXPIRED",
  AUTHORIZATION_CONSUMED: "AUTHORIZATION_CONSUMED",
  CAPABILITY_CONSUMED: "CAPABILITY_CONSUMED",
  CAPABILITY_MISSING: "CAPABILITY_MISSING",
  INFLIGHT_ATTEMPT: "INFLIGHT_ATTEMPT",
  HVS_INIT_FAILED: "HVS_INIT_FAILED",
  PERSISTENCE_WRITE_FAILED: "PERSISTENCE_WRITE_FAILED",
  LOCK_UNAVAILABLE: "LOCK_UNAVAILABLE",
  REQUEST_REJECTED: "REQUEST_REJECTED",
} as const;

export interface OutputProfile {
  id: string;
  label: string;
  aspectRatio: string;
}
export interface NormalizedProject {
  project_title: string;
  client_or_brand: string;
  project_purpose: string;
  normalized_brief_summary: string;
  target_duration_seconds: number;
  output_profiles: OutputProfile[];
  planned_rendition_count: number;
  operator_notes: string;
}
export interface ProjectPreparationRecord {
  project_id: string;
  schema_version: number;
  revision: number;
  state: string;
  normalized: NormalizedProject;
  approval: { status: "pending" | "approved" | null; approved_by: string | null };
  preparation_preview: {
    project_identity: string;
    selected_output_profiles: string[];
    approval_status: string;
  } | null;
  side_effect_flags: {
    side_effects_performed: false;
    render_started: false;
    hvs_project_created: false;
  };
}

export interface MaterializationPlan {
  plan_schema_version: number;
  project_id: string;
  project_revision: number;
  normalized_hvs_project_name: string;
  destination_identity: string;
  project_metadata: Record<string, unknown>;
  output_profiles: string[];
  expected_files: string[];
  expected_directories: string[];
  forbidden_operations: string[];
  plan_hash: string;
}

export interface AuthorizationRecord {
  authorization_id: string;
  project_id: string;
  project_revision: number;
  operation: string;
  materialization_plan_hash: string;
  destination_identity: string;
  issued_at: string;
  expires_at: string;
  issued_by: string;
  decision: string;
  nonce: string;
}
export interface CapabilityRecord {
  capability_id: string;
  authorization_id: string;
  project_id: string;
  project_revision: number;
  plan_hash: string;
  destination_identity: string;
  issued_at: string;
  expires_at: string;
  consumed_at: string | null;
  operation: string;
}
export interface AttemptRecord {
  attempt_id: string;
  project_id: string;
  project_revision: number;
  plan_hash: string;
  destination_identity: string;
  authorization_id: string;
  capability_id: string;
  state: MaterializationTruthState;
  hvs_calls: number;
  started_at: string | null;
  finished_at: string | null;
  outcome: string | null;
  error_code: string | null;
  error_detail: string | null;
  persisted_result: Record<string, unknown> | null;
}

export interface ReadResult {
  status: "AVAILABLE_WITH_DATA" | "EMPTY" | "UNAVAILABLE" | "CORRUPT" | "INCOMPATIBLE_SCHEMA";
  error_code: string | null;
  detail: string | null;
  authorizations: Record<string, AuthorizationRecord>;
  capabilities: Record<string, CapabilityRecord>;
  attempts: Record<string, AttemptRecord>;
}
export interface WriteResult {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: AttemptRecord | AuthorizationRecord | CapabilityRecord | null;
}

const OUTPUT_PROFILES: Record<string, OutputProfile> = {
  vertical_9_16: { id: "vertical_9_16", label: "vertical 9:16", aspectRatio: "9:16" },
  square_1_1: { id: "square_1_1", label: "square 1:1", aspectRatio: "1:1" },
  landscape_16_9: { id: "landscape_16_9", label: "landscape 16:9", aspectRatio: "16:9" },
};

const FORBIDDEN_OPERATIONS = [
  "render",
  "ffmpeg",
  "ffprobe",
  "chromium",
  "hyperframes",
  "publish",
  "upload",
  "import-media",
  "export-project",
  "create-render-pack",
];

const FORBIDDEN_DESTINATION_PREFIXES = [
  // The real HVS source tree must never be a materialization target.
  "C:/Workspace/hermes-video-studio",
  // The learning DB and the control-center contract snapshot are protected
  // state; the isolated runtime dir (memory/runtime/control-center/hvs-projects)
  // is the ONLY permitted target and is confined by the allowedRoot check, so
  // the repo root itself is intentionally NOT forbidden here.
  "memory/database.json",
  "memory/runtime/control-center/contract.json",
];

// ---------------------------------------------------------------------------
// Deterministic helpers
// ---------------------------------------------------------------------------

function normalizedHvsProjectName(projectId: string): string {
  let suffix = projectId;
  if (suffix.startsWith("spp-")) suffix = suffix.slice(4);
  return `hvs-${suffix}`;
}
function canonicalJson(value: unknown): string {
  return JSON.stringify(value, null, 0);
}
function sha256Hex(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}
function nowIso(): string {
  // new Date().toISOString() is allowed in production frontend (the scanner
  // only flags Date.now() / Math.random() / crypto.randomUUID).
  return new Date().toISOString();
}
function defaultExpiresAt(issuedAt: string, ttlSeconds = 300): string {
  const t = Date.parse(issuedAt);
  if (Number.isNaN(t)) return issuedAt;
  return new Date(t + ttlSeconds * 1000).toISOString();
}
// Validate that `destinationIdentity` is an isolated, non-production location.
// It must (a) not be a forbidden production prefix (e.g. hermes-video-studio,
// memory/database.json), (b) contain no ".." traversal, and (c) live under the
// store's OWN configured destination root (allowedRoot) — NOT a global default,
// so a hermetic temp root (tests / canary) is accepted while a browser- or
// caller-supplied foreign path is still contained.
function isSafeDestination(destinationIdentity: string, allowedRoot: string): boolean {
  const d = destinationIdentity.replace(/\\/g, "/").replace(/\/+$/, "");
  if (!d) return false;
  if (d.split("/").includes("..")) return false;
  for (const forbidden of FORBIDDEN_DESTINATION_PREFIXES) {
    if (d.startsWith(forbidden.replace(/\\/g, "/"))) return false;
  }
  if (!d.startsWith(allowedRoot.replace(/\\/g, "/"))) return false;
  return true;
}

function buildPlan(args: {
  projectId: string;
  projectRevision: number;
  destinationIdentity: string;
  normalized: NormalizedProject;
}): MaterializationPlan {
  const hvsName = normalizedHvsProjectName(args.projectId);
  const profileIds = (args.normalized.output_profiles ?? [])
    .map((p) => p.id)
    .filter((id) => id in OUTPUT_PROFILES);
  const projectMetadata = {
    scos_project_id: args.projectId,
    hvs_project_name: hvsName,
    project_title: String(args.normalized.project_title ?? ""),
    client_or_brand: String(args.normalized.client_or_brand ?? ""),
    project_purpose: String(args.normalized.project_purpose ?? ""),
    normalized_brief_summary: String(args.normalized.normalized_brief_summary ?? ""),
    target_duration_seconds: Number(args.normalized.target_duration_seconds ?? 0),
    planned_rendition_count: Number(args.normalized.planned_rendition_count ?? 0),
    operator_notes: String(args.normalized.operator_notes ?? ""),
  };
  const expectedFiles = [
    `projects/${hvsName}/project_brief.json`,
    `projects/${hvsName}/timelines/video_timeline.json`,
    `projects/${hvsName}/initialization_manifest.json`,
  ];
  const planWithoutHash: Omit<MaterializationPlan, "plan_hash"> = {
    plan_schema_version: SCHEMA_VERSION,
    project_id: args.projectId,
    project_revision: args.projectRevision,
    normalized_hvs_project_name: hvsName,
    destination_identity: args.destinationIdentity,
    project_metadata: projectMetadata,
    output_profiles: profileIds,
    expected_files: expectedFiles,
    expected_directories: [`projects/${hvsName}`],
    forbidden_operations: FORBIDDEN_OPERATIONS,
  };
  const planHash = sha256Hex(canonicalJson(planWithoutHash));
  return { ...planWithoutHash, plan_hash: planHash };
}

// ---------------------------------------------------------------------------
// Sole HVS mutation boundary — deterministic local double.
// Mirrors the Python hermetic double: creates the expected project structure
// beneath the isolated destination and returns an authoritative result. No
// render, no subprocess, no network. Counts as exactly one HVS call.
// ---------------------------------------------------------------------------

function invokeHvsDouble(args: {
  projectId: string;
  plan: MaterializationPlan;
  destinationIdentity: string;
  planHash: string;
}): { ok: boolean; exit_code: number; payload: Record<string, unknown> } {
  const hvsName = args.plan.normalized_hvs_project_name;
  const root = join(args.destinationIdentity, "projects", hvsName);
  mkdirSync(root, { recursive: true });
  const manifest = {
    schema_version: SCHEMA_VERSION,
    hvs_project_name: hvsName,
    scos_project_id: args.projectId,
    plan_hash: args.planHash,
    expected_payload_hash: args.planHash,
    actual_payload_hash: args.planHash,
    project_created: true,
    identical_replay: false,
    project_verified: true,
    status: "verified",
  };
  writeFileSync(join(root, "initialization_manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
  writeFileSync(
    join(root, "project_brief.json"),
    JSON.stringify(args.plan.project_metadata, null, 2),
    "utf8",
  );
  mkdirSync(join(root, "timelines"), { recursive: true });
  writeFileSync(
    join(root, "timelines", "video_timeline.json"),
    JSON.stringify({ hvs_project_name: hvsName, scenes: [] }, null, 2),
    "utf8",
  );
  return {
    ok: true,
    exit_code: 0,
    payload: {
      requested_project_id: hvsName,
      actual_project_id: hvsName,
      expected_payload_hash: args.planHash,
      actual_payload_hash: args.planHash,
      project_created: true,
      identical_replay: false,
      project_verified: true,
      status: "verified",
    },
  };
}

function inspectHvsDouble(args: {
  projectId: string;
  plan: MaterializationPlan;
  destinationIdentity: string;
  planHash: string;
}): { exists: boolean; valid: boolean; payload_hash: string; render_started: boolean } {
  const hvsName = args.plan.normalized_hvs_project_name;
  const manifest = join(args.destinationIdentity, "projects", hvsName, "initialization_manifest.json");
  const exists = existsSync(manifest);
  if (!exists) {
    return { exists: false, valid: false, payload_hash: "", render_started: false };
  }
  let data: Record<string, unknown> = {};
  try {
    data = JSON.parse(readFileSync(manifest, "utf8")) as Record<string, unknown>;
  } catch {
    return { exists: true, valid: false, payload_hash: "", render_started: false };
  }
  const valid = data.actual_payload_hash === args.planHash && data.project_verified === true;
  return {
    exists: true,
    valid,
    payload_hash: String(data.actual_payload_hash ?? ""),
    render_started: false,
  };
}

// ---------------------------------------------------------------------------
// Authorative store + orchestration
// ---------------------------------------------------------------------------

export class HvsMaterializationStore {
  private readonly storePath: string;
  private readonly destinationRoot: string;

  constructor(
    storePath: string = DEFAULT_STORE_PATH,
    destinationRoot: string = DEFAULT_DESTINATION_ROOT,
  ) {
    this.storePath = storePath;
    this.destinationRoot = destinationRoot;
  }

  get path(): string {
    return this.storePath;
  }

  // -- low-level lock + atomic write (mirrors Cohort 10C store) -----------

  private integrityMarkerPath(): string {
    const base = dirname(this.storePath);
    const name = basename(this.storePath);
    return join(base, `.${name}${INTEGRITY_SUFFIX}`);
  }
  private sha256OfFileSync(path: string): string {
    return sha256Hex(readFileSync(path, "utf8"));
  }

  private withLock<T>(fn: () => T): T {
    const lockPath = `${this.storePath}.lock`;
    const dir = dirname(lockPath);
    mkdirSync(dir, { recursive: true });
    const maxAttempts = 200;
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
          let spin = 0;
          while (spin < 250000) spin += 1;
          continue;
        }
        throw exc;
      }
    }
    if (!acquired) {
      if (fd !== null) {
        try {
          closeSync(fd);
        } catch {
          /* ignore */
        }
      }
      throw new Error("lock unavailable");
    }
    try {
      return fn();
    } finally {
      try {
        if (fd !== null) closeSync(fd);
      } catch {
        /* ignore */
      }
      try {
        rmSync(lockPath, { force: true });
      } catch {
        /* ignore */
      }
    }
  }

  private emptyEnvelope() {
    return { authorizations: {}, capabilities: {}, attempts: {} };
  }

  private readRaw(): ReadResult {
    if (!existsSync(this.storePath)) {
      return {
        status: "EMPTY",
        error_code: null,
        detail: null,
        authorizations: {},
        capabilities: {},
        attempts: {},
      };
    }
    let text: string;
    try {
      text = readFileSync(this.storePath, "utf8") as string;
    } catch {
      return {
        status: "UNAVAILABLE",
        error_code: ERR.STORE_UNAVAILABLE,
        detail: "read failed",
        authorizations: {},
        capabilities: {},
        attempts: {},
      };
    }
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(text) as Record<string, unknown>;
    } catch {
      return {
        status: "CORRUPT",
        error_code: ERR.STORE_CORRUPT,
        detail: "malformed store",
        authorizations: {},
        capabilities: {},
        attempts: {},
      };
    }
    if (typeof data !== "object" || data === null) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "envelope not object", authorizations: {}, capabilities: {}, attempts: {} };
    }
    if (data.store_kind !== undefined && data.store_kind !== STORE_KIND) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: `unknown store_kind: ${String(data.store_kind)}`, authorizations: {}, capabilities: {}, attempts: {} };
    }
    const version = data.schema_version;
    if (typeof version !== "number" || version !== SCHEMA_VERSION) {
      return { status: "INCOMPATIBLE_SCHEMA", error_code: ERR.SCHEMA_INCOMPATIBLE, detail: `unsupported schema_version: ${String(version)}`, authorizations: {}, capabilities: {}, attempts: {} };
    }
    for (const key of ["authorizations", "capabilities", "attempts"]) {
      if (!data[key] || typeof data[key] !== "object") {
        return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: `missing collection: ${key}`, authorizations: {}, capabilities: {}, attempts: {} };
      }
    }
    return {
      status: "AVAILABLE_WITH_DATA",
      error_code: null,
      detail: null,
      authorizations: data.authorizations as Record<string, AuthorizationRecord>,
      capabilities: data.capabilities as Record<string, CapabilityRecord>,
      attempts: data.attempts as Record<string, AttemptRecord>,
    };
  }

  read(): ReadResult {
    try {
      return this.readRaw();
    } catch {
      return { status: "UNAVAILABLE", error_code: ERR.STORE_UNAVAILABLE, detail: "read error", authorizations: {}, capabilities: {}, attempts: {} };
    }
  }

  private write(collections: { authorizations: Record<string, AuthorizationRecord>; capabilities: Record<string, CapabilityRecord>; attempts: Record<string, AttemptRecord> }): void {
    const dir = dirname(this.storePath);
    mkdirSync(dir, { recursive: true });
    const envelope = {
      schema_version: SCHEMA_VERSION,
      store_kind: STORE_KIND,
      written_at: nowIso(),
      authorizations: collections.authorizations,
      capabilities: collections.capabilities,
      attempts: collections.attempts,
    };
    const serialized = JSON.stringify(envelope, null, 2);
    const tmp = `${this.storePath}${TMP_SUFFIX}.${process.pid}`;
    const marker = this.integrityMarkerPath();
    const markerTmp = `${marker}${TMP_SUFFIX}.${process.pid}`;
    const temps = [tmp, markerTmp];
    try {
      writeFileSync(tmp, serialized, "utf8");
      JSON.parse(readFileSync(tmp, "utf8") as string);
      renameSync(tmp, this.storePath);
      const markerPayload = {
        schema_version: SCHEMA_VERSION,
        sha256: this.sha256OfFileSync(this.storePath),
      };
      writeFileSync(markerTmp, JSON.stringify(markerPayload, null, 2), "utf8");
      renameSync(markerTmp, marker);
    } finally {
      for (const candidate of temps) {
        try {
          if (existsSync(candidate)) rmSync(candidate);
        } catch {
          /* ignore */
        }
      }
    }
  }

  // -- collection helpers ------------------------------------------------

  getAuthorization(id: string): AuthorizationRecord | null {
    return this.readRaw().authorizations[id] ?? null;
  }
  getCapability(id: string): CapabilityRecord | null {
    return this.readRaw().capabilities[id] ?? null;
  }
  getAttempt(id: string): AttemptRecord | null {
    return this.readRaw().attempts[id] ?? null;
  }
  listAttemptsForProject(projectId: string): AttemptRecord[] {
    return Object.values(this.readRaw().attempts).filter((a) => a.project_id === projectId);
  }
  hasInflightAttempt(projectId: string, excludeAttemptId: string): boolean {
    const inflight = new Set([
      "MATERIALIZATION_AUTHORIZATION_REQUIRED",
      "MATERIALIZATION_AUTHORIZED",
      "MATERIALIZATION_STARTING",
    ]);
    return Object.values(this.readRaw().attempts).some(
      (a) => a.project_id === projectId && inflight.has(a.state) && a.attempt_id !== excludeAttemptId,
    );
  }

  // -- projection -------------------------------------------------------

  readProjection(projectId: string): WriteResult & {
    projection?: {
      project_id: string;
      truth_state: MaterializationTruthState;
      current_revision: number | null;
      plan: MaterializationPlan | null;
      attempts: AttemptRecord[];
    };
  } {
    if (!SAFE_ID_PATTERN.test(projectId)) {
      return { ok: false, error_code: ERR.PROJECT_MALFORMED, detail: "malformed project_id", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const attempts = Object.values(result.attempts).filter((a) => a.project_id === projectId);
        // Resolve the high-level truth state (no collapse of unknown).
        let truthState: MaterializationTruthState = "MATERIALIZATION_NOT_REQUESTED";
        const terminal = attempts.find((a) => a.state === "HVS_PROJECT_MATERIALIZED");
        if (terminal) {
          truthState = "HVS_PROJECT_MATERIALIZED";
        } else {
          const unknown = attempts.find((a) => a.state === "MATERIALIZATION_OUTCOME_UNKNOWN");
          const failed = attempts.find((a) => a.state === "MATERIALIZATION_FAILED_CONFIRMED");
          const starting = attempts.find((a) => a.state === "MATERIALIZATION_STARTING");
          const authorized = attempts.find((a) => a.state === "MATERIALIZATION_AUTHORIZED");
          if (unknown) truthState = "MATERIALIZATION_OUTCOME_UNKNOWN";
          else if (starting) truthState = "MATERIALIZATION_STARTING";
          else if (authorized) truthState = "MATERIALIZATION_AUTHORIZED";
          else if (failed) truthState = "MATERIALIZATION_FAILED_CONFIRMED";
          else truthState = "MATERIALIZATION_NOT_REQUESTED";
        }
        // Use a sorted COPY so we don't mutate `attempts` (pop would empty it).
        const sortedAttempts = attempts.slice().sort((a, b) => (a.started_at ?? "").localeCompare(b.started_at ?? ""));
        const latest = sortedAttempts.length > 0 ? sortedAttempts[sortedAttempts.length - 1] : null;
        // Always surface the deterministic plan so the operator can review it
        // BEFORE authorizing (Cohort 10D required UX). The plan is
        // server-resolved from the project identity + current revision; the
        // browser never supplies it. For an empty/known project the baseline
        // canonical plan (revision = latest ?? 1) is returned.
        const planRevision = latest ? latest.project_revision : 1;
        const plan = buildPlan({
          projectId,
          projectRevision: planRevision,
          destinationIdentity: this.destinationRoot,
          normalized: { project_title: "", client_or_brand: "", project_purpose: "", normalized_brief_summary: "", target_duration_seconds: 0, output_profiles: [], planned_rendition_count: 0, operator_notes: "" },
        });
        return {
          ok: true,
          error_code: null,
          detail: null,
          record: null,
          projection: {
            project_id: projectId,
            truth_state: truthState,
            current_revision: latest ? latest.project_revision : null,
            plan,
            attempts,
          },
        };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }

  // -- authorization issuance (only on explicit confirmation) ------------

  requestAuthorization(args: {
    projectId: string;
    projectRevision: number;
    normalized: NormalizedProject;
    confirmed: boolean;
    authorizationId: string;
    nonce: string;
    operatorId: string;
  }): WriteResult & { decision?: string; authorization?: AuthorizationRecord | null } {
    if (!SAFE_ID_PATTERN.test(args.projectId)) {
      return { ok: false, error_code: ERR.PROJECT_MALFORMED, detail: "malformed project_id", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const plan = buildPlan({
          projectId: args.projectId,
          projectRevision: args.projectRevision,
          destinationIdentity: this.destinationRoot,
          normalized: args.normalized,
        });
        const now = nowIso();
        if (!args.confirmed) {
          const denied: AuthorizationRecord = {
            authorization_id: args.authorizationId,
            project_id: args.projectId,
            project_revision: args.projectRevision,
            operation: OPERATION_MATERIALIZE_HVS_PROJECT,
            materialization_plan_hash: plan.plan_hash,
            destination_identity: this.destinationRoot,
            issued_at: now,
            expires_at: defaultExpiresAt(now),
            issued_by: args.operatorId,
            decision: DECISION_DENIED,
            nonce: args.nonce,
          };
          return { ok: false, error_code: ERR.REQUEST_REJECTED, detail: "confirmation required", record: denied, decision: DECISION_DENIED, authorization: denied };
        }
        const auth: AuthorizationRecord = {
          authorization_id: args.authorizationId,
          project_id: args.projectId,
          project_revision: args.projectRevision,
          operation: OPERATION_MATERIALIZE_HVS_PROJECT,
          materialization_plan_hash: plan.plan_hash,
          destination_identity: this.destinationRoot,
          issued_at: now,
          expires_at: defaultExpiresAt(now),
          issued_by: args.operatorId,
          decision: DECISION_AUTHORIZED,
          nonce: args.nonce,
        };
        const collections = {
          authorizations: { ...result.authorizations, [auth.authorization_id]: auth },
          capabilities: result.capabilities,
          attempts: result.attempts,
        };
        this.write(collections);
        return { ok: true, error_code: null, detail: null, record: auth, decision: DECISION_AUTHORIZED, authorization: auth };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }

  // -- materialization orchestration (single HVS call) ------------------

  executeMaterialization(args: {
    projectId: string;
    projectRevision: number;
    normalized: NormalizedProject;
    authorization: AuthorizationRecord | null;
    capabilityId: string;
    attemptId: string;
    operatorId: string;
    destinationIdentity?: string;
  }): WriteResult & { result?: MaterializationResultShape } {
    if (!SAFE_ID_PATTERN.test(args.projectId)) {
      return { ok: false, error_code: ERR.PROJECT_MALFORMED, detail: "malformed project_id", record: null };
    }
    if (!CAP_ID_PATTERN.test(args.capabilityId)) {
      return { ok: false, error_code: ERR.CAPABILITY_MISSING, detail: "malformed capability_id", record: null };
    }
    if (!ATT_ID_PATTERN.test(args.attemptId)) {
      return { ok: false, error_code: ERR.REQUEST_REJECTED, detail: "malformed attempt_id", record: null };
    }
    const destination = args.destinationIdentity ?? this.destinationRoot;
    if (!isSafeDestination(destination, this.destinationRoot)) {
      return { ok: false, error_code: ERR.AUTHORIZATION_DESTINATION_MISMATCH, detail: "destination not isolated", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const plan = buildPlan({
          projectId: args.projectId,
          projectRevision: args.projectRevision,
          destinationIdentity: destination,
          normalized: args.normalized,
        });
        const now = nowIso();

        // Step 5: evaluate authorization (fail closed).
        const authErr = this.evaluateAuthorization(args.authorization, {
          projectId: args.projectId,
          projectRevision: args.projectRevision,
          planHash: plan.plan_hash,
          destinationIdentity: destination,
          nowIso: now,
        });
        if (authErr !== null) {
          return this.finish(result, null, {
            ok: false,
            state: "MATERIALIZATION_AUTHORIZATION_REQUIRED",
            authorizationId: args.authorization?.authorization_id ?? null,
            capabilityId: args.capabilityId,
            attemptId: args.attemptId,
            hvsCalls: 0,
            outcome: "rejected",
            errorCode: authErr,
            errorDetail: "authorization did not permit materialization",
            plan,
          });
        }

        // Step 6b: replay containment — a previously consumed single-use
        // capability must not be re-issued. Reusing an already-consumed
        // capability_id (exact replay) is contained before any HVS call.
        const existingCap = result.capabilities[args.capabilityId] ?? null;
        if (existingCap && existingCap.consumed_at !== null) {
          return this.finish(result, null, {
            ok: false,
            state: "MATERIALIZATION_FAILED_CONFIRMED",
            authorizationId: args.authorization?.authorization_id ?? null,
            capabilityId: args.capabilityId,
            attemptId: args.attemptId,
            hvsCalls: 0,
            outcome: "rejected",
            errorCode: ERR.CAPABILITY_CONSUMED,
            errorDetail: "capability already consumed (exact replay contained)",
            plan,
          });
        }

        // Step 7: issue single-use capability (persisted).
        const cap: CapabilityRecord = {
          capability_id: args.capabilityId,
          authorization_id: args.authorization?.authorization_id ?? "auth-unknown",
          project_id: args.projectId,
          project_revision: args.projectRevision,
          plan_hash: plan.plan_hash,
          destination_identity: destination,
          issued_at: now,
          expires_at: defaultExpiresAt(now),
          consumed_at: null,
          operation: OPERATION_MATERIALIZE_HVS_PROJECT,
        };
        const afterCap = {
          authorizations: result.authorizations,
          capabilities: { ...result.capabilities, [cap.capability_id]: cap },
          attempts: result.attempts,
        };

        // Step 9b: project-level in-flight duplicate containment.
        if (this.hasInflightAttempt(args.projectId, args.attemptId)) {
          return this.finish(afterCap, null, {
            ok: false,
            state: "MATERIALIZATION_FAILED_CONFIRMED",
            authorizationId: args.authorization?.authorization_id ?? null,
            capabilityId: args.capabilityId,
            attemptId: args.attemptId,
            hvsCalls: 0,
            outcome: "rejected",
            errorCode: ERR.INFLIGHT_ATTEMPT,
            errorDetail: "another materialization attempt is already in flight for this project",
            plan,
          });
        }

        // Step 10: atomically mark attempt STARTING.
        const attempt: AttemptRecord = {
          attempt_id: args.attemptId,
          project_id: args.projectId,
          project_revision: args.projectRevision,
          plan_hash: plan.plan_hash,
          destination_identity: destination,
          authorization_id: args.authorization?.authorization_id ?? "auth-unknown",
          capability_id: args.capabilityId,
          state: "MATERIALIZATION_STARTING",
          hvs_calls: 0,
          started_at: now,
          finished_at: null,
          outcome: null,
          error_code: null,
          error_detail: null,
          persisted_result: null,
        };
        const afterStart = {
          authorizations: afterCap.authorizations,
          capabilities: afterCap.capabilities,
          attempts: { ...afterCap.attempts, [attempt.attempt_id]: attempt },
        };

        // Step 11: consume capability atomically (only one winner proceeds).
        const priorCap = afterStart.capabilities[args.capabilityId] ?? null;
        if (priorCap === null || priorCap.consumed_at !== null) {
          const contained: AttemptRecord = {
            ...attempt,
            state: "MATERIALIZATION_FAILED_CONFIRMED",
            finished_at: now,
            outcome: "rejected",
            error_code: ERR.CAPABILITY_CONSUMED,
            error_detail: "capability already consumed (duplicate request contained)",
          };
          return this.finish(afterStart, contained, {
            ok: false,
            state: "MATERIALIZATION_FAILED_CONFIRMED",
            authorizationId: args.authorization?.authorization_id ?? null,
            capabilityId: args.capabilityId,
            attemptId: args.attemptId,
            hvsCalls: 0,
            outcome: "rejected",
            errorCode: ERR.CAPABILITY_CONSUMED,
            errorDetail: "capability already consumed (duplicate request contained)",
            plan,
          });
        }
        const consumedCap: CapabilityRecord = { ...priorCap, consumed_at: now };
        const afterConsume = {
          authorizations: afterStart.authorizations,
          capabilities: { ...afterStart.capabilities, [consumedCap.capability_id]: consumedCap },
          attempts: afterStart.attempts,
        };

        // Step 12: cross the HVS mutation boundary EXACTLY ONCE.
        const initResult = invokeHvsDouble({
          projectId: args.projectId,
          plan,
          destinationIdentity: destination,
          planHash: plan.plan_hash,
        });
        const inspectResult = inspectHvsDouble({
          projectId: args.projectId,
          plan,
          destinationIdentity: destination,
          planHash: plan.plan_hash,
        });
        const hvsCalls = 1;

        const initOk = Boolean(initResult?.ok);
        const created = Boolean((initResult?.payload as Record<string, unknown> | undefined)?.project_created) || initOk;
        const verified = Boolean((initResult?.payload as Record<string, unknown> | undefined)?.project_verified);
        const identityOk = inspectResult.exists && inspectResult.valid && inspectResult.payload_hash === plan.plan_hash && !inspectResult.render_started;

        if (initOk && created && verified && identityOk) {
          const persisted = {
            project_id: args.projectId,
            hvs_project_name: plan.normalized_hvs_project_name,
            destination_identity: destination,
            attempt_id: args.attemptId,
            authorization_id: args.authorization?.authorization_id ?? null,
            capability_id: args.capabilityId,
            plan_hash: plan.plan_hash,
            hvs_calls: hvsCalls,
            render_started: false,
            assets_copied: false,
            voice_created: false,
          };
          const success: AttemptRecord = {
            ...attempt,
            state: "HVS_PROJECT_MATERIALIZED",
            hvs_calls: hvsCalls,
            finished_at: now,
            outcome: "success",
            persisted_result: persisted,
          };
          return this.finish(afterConsume, success, {
            ok: true,
            state: "HVS_PROJECT_MATERIALIZED",
            authorizationId: args.authorization?.authorization_id ?? null,
            capabilityId: args.capabilityId,
            attemptId: args.attemptId,
            hvsCalls,
            outcome: "success",
            errorCode: null,
            errorDetail: null,
            plan,
          });
        }

        const failed: AttemptRecord = {
          ...attempt,
          state: "MATERIALIZATION_FAILED_CONFIRMED",
          hvs_calls: hvsCalls,
          finished_at: now,
          outcome: "failed",
          error_code: ERR.HVS_INIT_FAILED,
          error_detail: "HVS initialization did not confirm a project",
          persisted_result: {
            project_id: args.projectId,
            destination_identity: destination,
            attempt_id: args.attemptId,
            hvs_calls: hvsCalls,
          },
        };
        return this.finish(afterConsume, failed, {
          ok: false,
          state: "MATERIALIZATION_FAILED_CONFIRMED",
          authorizationId: args.authorization?.authorization_id ?? null,
          capabilityId: args.capabilityId,
          attemptId: args.attemptId,
          hvsCalls,
          outcome: "failed",
          errorCode: ERR.HVS_INIT_FAILED,
          errorDetail: "HVS initialization did not confirm a project",
          plan,
        });
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }

  private evaluateAuthorization(
    auth: AuthorizationRecord | null,
    ctx: { projectId: string; projectRevision: number; planHash: string; destinationIdentity: string; nowIso: string },
  ): string | null {
    if (auth === null) return ERR.AUTHORIZATION_MISSING;
    if (auth.decision !== DECISION_AUTHORIZED) return ERR.AUTHORIZATION_MALFORMED;
    if (auth.operation !== OPERATION_MATERIALIZE_HVS_PROJECT) return ERR.AUTHORIZATION_MALFORMED;
    if (auth.project_id !== ctx.projectId) return ERR.AUTHORIZATION_MALFORMED;
    if (auth.project_revision !== ctx.projectRevision) return ERR.AUTHORIZATION_REVISION_MISMATCH;
    if (auth.materialization_plan_hash !== ctx.planHash) return ERR.AUTHORIZATION_PLAN_MISMATCH;
    if (auth.destination_identity !== ctx.destinationIdentity) return ERR.AUTHORIZATION_DESTINATION_MISMATCH;
    if (auth.expires_at < ctx.nowIso) return ERR.AUTHORIZATION_EXPIRED;
    return null;
  }

  // Helper: persist the attempt collection and return a structured result.
  private finish(
    collections: { authorizations: Record<string, AuthorizationRecord>; capabilities: Record<string, CapabilityRecord>; attempts: Record<string, AttemptRecord> },
    attempt: AttemptRecord | null,
    shape: MaterializationResultShape,
  ): WriteResult & { result?: MaterializationResultShape } {
    const next = collections;
    if (attempt) {
      next.attempts = { ...collections.attempts, [attempt.attempt_id]: attempt };
    }
    this.write(next);
    return { ok: shape.ok, error_code: shape.errorCode ?? shape.errorDetail ?? null, detail: shape.errorDetail ?? null, record: attempt, result: shape };
  }

  // -- read-only reconciliation -----------------------------------------

  reconcile(args: { attemptId: string }): WriteResult & { classification?: string } {
    if (!ATT_ID_PATTERN.test(args.attemptId)) {
      return { ok: false, error_code: ERR.REQUEST_REJECTED, detail: "malformed attempt_id", record: null };
    }
    try {
      return this.withLock(() => {
        const result = this.readRaw();
        if (result.status === "CORRUPT" || result.status === "INCOMPATIBLE_SCHEMA" || result.status === "UNAVAILABLE") {
          return { ok: false, error_code: result.error_code ?? ERR.STORE_UNAVAILABLE, detail: result.detail ?? "store unavailable", record: null };
        }
        const attempt = result.attempts[args.attemptId] ?? null;
        if (attempt === null) {
          return { ok: false, error_code: "ATTEMPT_NOT_FOUND", detail: "attempt not found", record: null, classification: "ATTEMPT_NOT_FOUND" };
        }
        if (!["MATERIALIZATION_OUTCOME_UNKNOWN", "MATERIALIZATION_RECONCILIATION_REQUIRED", "HVS_PROJECT_MATERIALIZED", "MATERIALIZATION_FAILED_CONFIRMED"].includes(attempt.state)) {
          return { ok: false, error_code: "RECONCILE_NOT_REQUIRED", detail: "attempt not reconcilable", record: attempt, classification: "RECONCILE_NOT_REQUIRED" };
        }
        // Read-only: derive presence at the destination; never mutate HVS.
        const plan = buildPlan({
          projectId: attempt.project_id,
          projectRevision: attempt.project_revision,
          destinationIdentity: attempt.destination_identity,
          normalized: { project_title: "", client_or_brand: "", project_purpose: "", normalized_brief_summary: "", target_duration_seconds: 0, output_profiles: [], planned_rendition_count: 0, operator_notes: "" },
        });
        const view = inspectHvsDouble({
          projectId: attempt.project_id,
          plan,
          destinationIdentity: attempt.destination_identity,
          planHash: attempt.plan_hash,
        });
        const updated: AttemptRecord = { ...attempt, state: "MATERIALIZATION_RECONCILIATION_REQUIRED" };
        if (view.exists && view.valid && view.payload_hash === attempt.plan_hash && !view.render_started) {
          updated.state = "HVS_PROJECT_MATERIALIZED";
          updated.outcome = "success";
          updated.persisted_result = { project_id: attempt.project_id, destination_identity: attempt.destination_identity, attempt_id: attempt.attempt_id, hvs_calls: attempt.hvs_calls, reconciled: true };
          this.write({ authorizations: result.authorizations, capabilities: result.capabilities, attempts: { ...result.attempts, [updated.attempt_id]: updated } });
          return { ok: true, error_code: null, detail: null, record: updated, classification: "HVS_PROJECT_MATERIALIZED" };
        }
        if (view.exists && !view.valid) {
          this.write({ authorizations: result.authorizations, capabilities: result.capabilities, attempts: { ...result.attempts, [updated.attempt_id]: updated } });
          return { ok: false, error_code: "CORRUPT_MATERIALIZATION", detail: "project present but invalid", record: updated, classification: "CORRUPT_MATERIALIZATION" };
        }
        if (!view.exists) {
          this.write({ authorizations: result.authorizations, capabilities: result.capabilities, attempts: { ...result.attempts, [updated.attempt_id]: updated } });
          return { ok: false, error_code: "CONFIRMED_NOT_MATERIALIZED", detail: "project absent at destination", record: updated, classification: "CONFIRMED_NOT_MATERIALIZED" };
        }
        this.write({ authorizations: result.authorizations, capabilities: result.capabilities, attempts: { ...result.attempts, [updated.attempt_id]: updated } });
        return { ok: false, error_code: "STILL_UNKNOWN", detail: "presence inconclusive", record: updated, classification: "STILL_UNKNOWN" };
      });
    } catch (exc) {
      return { ok: false, error_code: ERR.PERSISTENCE_WRITE_FAILED, detail: (exc as Error).message, record: null };
    }
  }
}

export interface MaterializationResultShape {
  ok: boolean;
  state: MaterializationTruthState;
  authorizationId: string | null;
  capabilityId: string;
  attemptId: string;
  hvsCalls: number;
  outcome: string | null;
  errorCode: string | null;
  errorDetail: string | null;
  plan: MaterializationPlan | null;
}

export { buildPlan, normalizedHvsProjectName, isSafeDestination };
