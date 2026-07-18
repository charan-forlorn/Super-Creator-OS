/**
 * Phase 2 — authoritative local persistence for Brand Kits.
 *
 * Mirrors apps/control-center/lib/project-preparation-store.ts 1:1 (same
 * atomic-write / advisory-lock / fail-closed contract, same store directory
 * under memory/runtime/control-center/). Brand Kits are a local-only,
 * server-resolved resource; the browser never supplies a path or URL.
 *
 * Allowed truth states (every read resolves to exactly one):
 *   AVAILABLE_WITH_DATA | EMPTY | UNAVAILABLE | CORRUPT | INCOMPATIBLE_SCHEMA
 */

import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join } from "node:path";

// Anchored to the app package root via process.cwd() (Next runs from
// apps/control-center, so ../.. reaches the repo root), resolving to
// repo-root memory/runtime/control-center/brand-kit-v1.json — the same
// directory as the project-preparation store. Route handlers must import
// brandKitStorePath() and MUST NOT recompute a caller-relative path.
const DEFAULT_STORE_PATH = join(
  process.cwd(),
  "..",
  "..",
  "memory",
  "runtime",
  "control-center",
  "brand-kit-v1.json",
);
const INTEGRITY_SUFFIX = ".integrity.json";
const TMP_SUFFIX = ".tmp";

export function brandKitStorePath(): string {
  return DEFAULT_STORE_PATH;
}

export const STORE_KIND = "scos.brand_kit.v1";
export const SCHEMA_VERSION = 1;

export type TruthStatus =
  | "AVAILABLE_WITH_DATA"
  | "EMPTY"
  | "UNAVAILABLE"
  | "CORRUPT"
  | "INCOMPATIBLE_SCHEMA";

export interface BrandKit {
  brand_kit_id: string;
  schema_version: number;
  name: string;
  colors: { primary: string; secondary: string; accent: string; neutrals: string[] };
  fonts: { heading: string; body: string };
  logo: { asset_ref: string; kind: "local-ref" };
  contact: { name: string; email: string; socials: { label: string; handle: string }[] };
  basic_cta: { label: string; target: string };
}

export interface StoreEnvelope {
  schema_version: number;
  store_kind: string;
  written_at: string;
  record_count: number;
  records: BrandKit[];
}

export interface ReadResult {
  status: TruthStatus;
  error_code: string | null;
  detail: string | null;
  records: BrandKit[];
}

export interface WriteResult {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: BrandKit | null;
}

export const ERR = {
  STORE_UNAVAILABLE: "STORE_UNAVAILABLE",
  STORE_CORRUPT: "STORE_CORRUPT",
  SCHEMA_INCOMPATIBLE: "SCHEMA_INCOMPATIBLE",
  PERSISTENCE_WRITE_FAILED: "PERSISTENCE_WRITE_FAILED",
  LOCK_UNAVAILABLE: "LOCK_UNAVAILABLE",
} as const;

// Deterministic id (FNV-1a JS, matching the project-preparation stableId family).
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

export function deriveBrandKitId(name: string): string {
  return `bkb-${fnv1aJsUtf16(name.toLowerCase())}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function sha256OfFileSync(path: string): string {
  const buf = readFileSync(path);
  return createHash("sha256").update(buf).digest("hex");
}

export interface BrandKitInput {
  name: string;
  colors: { primary: string; secondary: string; accent: string; neutrals: string[] };
  fonts: { heading: string; body: string };
  logo: { asset_ref: string; kind: "local-ref" };
  contact: { name: string; email: string; socials: { label: string; handle: string }[] };
  basic_cta: { label: string; target: string };
}

export function validateBrandKitInput(input: BrandKitInput): string[] {
  const errors: string[] = [];
  if (!input.name || !input.name.trim()) errors.push("NAME_REQUIRED");
  if (!input.colors?.primary) errors.push("PRIMARY_COLOR_REQUIRED");
  if (!input.colors?.secondary) errors.push("SECONDARY_COLOR_REQUIRED");
  if (!input.colors?.accent) errors.push("ACCENT_COLOR_REQUIRED");
  if (!input.fonts?.heading) errors.push("HEADING_FONT_REQUIRED");
  if (!input.fonts?.body) errors.push("BODY_FONT_REQUIRED");
  if (!input.logo?.asset_ref) errors.push("LOGO_REF_REQUIRED");
  if (!input.contact?.name) errors.push("CONTACT_NAME_REQUIRED");
  if (!input.contact?.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(input.contact.email)) {
    errors.push("CONTACT_EMAIL_INVALID");
  }
  if (!input.basic_cta?.label) errors.push("CTA_LABEL_REQUIRED");
  if (!input.basic_cta?.target) errors.push("CTA_TARGET_REQUIRED");
  return [...new Set(errors)].sort();
}

function normalizeInput(input: BrandKitInput): BrandKit {
  return {
    brand_kit_id: deriveBrandKitId(input.name),
    schema_version: SCHEMA_VERSION,
    name: input.name.trim(),
    colors: {
      primary: input.colors.primary,
      secondary: input.colors.secondary,
      accent: input.colors.accent,
      neutrals: Array.isArray(input.colors.neutrals) ? input.colors.neutrals : [],
    },
    fonts: { heading: input.fonts.heading, body: input.fonts.body },
    logo: { asset_ref: input.logo.asset_ref, kind: "local-ref" },
    contact: {
      name: input.contact.name,
      email: input.contact.email,
      socials: Array.isArray(input.contact.socials) ? input.contact.socials : [],
    },
    basic_cta: { label: input.basic_cta.label, target: input.basic_cta.target },
  };
}

export class BrandKitStore {
  private readonly storePath: string;

  constructor(storePath: string = DEFAULT_STORE_PATH) {
    this.storePath = storePath;
  }

  get path(): string {
    return this.storePath;
  }

  private integrityMarkerPath(): string {
    const base = dirname(this.storePath);
    const name = basename(this.storePath);
    return join(base, `.${name}${INTEGRITY_SUFFIX}`);
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
    if (data.schema_version !== SCHEMA_VERSION) {
      return {
        status: "INCOMPATIBLE_SCHEMA",
        error_code: ERR.SCHEMA_INCOMPATIBLE,
        detail: `unsupported schema_version: ${data.schema_version}`,
        records: [],
      };
    }
    if (!Array.isArray(data.records)) {
      return { status: "CORRUPT", error_code: ERR.STORE_CORRUPT, detail: "records not list", records: [] };
    }
    if (data.records.length === 0) {
      return { status: "EMPTY", error_code: null, detail: null, records: [] };
    }
    return { status: "AVAILABLE_WITH_DATA", error_code: null, detail: null, records: data.records };
  }

  read(): ReadResult {
    try {
      return this.readRaw();
    } catch {
      return { status: "UNAVAILABLE", error_code: ERR.STORE_UNAVAILABLE, detail: "read error", records: [] };
    }
  }

  private write(records: BrandKit[]): void {
    const dir = dirname(this.storePath);
    mkdirSync(dir, { recursive: true });
    const envelope: StoreEnvelope = {
      schema_version: SCHEMA_VERSION,
      store_kind: STORE_KIND,
      written_at: nowIso(),
      record_count: records.length,
      records,
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
        sha256: sha256OfFileSync(this.storePath),
        record_count: records.length,
        written_at: envelope.written_at,
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

  upsert(input: BrandKitInput): WriteResult {
    const errors = validateBrandKitInput(input);
    if (errors.length > 0) {
      return { ok: false, error_code: "VALIDATION_FAILED", detail: errors.join("; "), record: null };
    }
    try {
      const normalized = normalizeInput(input);
      const existing = this.read();
      const records =
        existing.status === "AVAILABLE_WITH_DATA" || existing.status === "EMPTY"
          ? existing.records.filter((r) => r.brand_kit_id !== normalized.brand_kit_id)
          : [];
      records.push(normalized);
      this.write(records);
      return { ok: true, error_code: null, detail: null, record: normalized };
    } catch (exc) {
      return {
        ok: false,
        error_code: ERR.PERSISTENCE_WRITE_FAILED,
        detail: exc instanceof Error ? exc.message : "write failed",
        record: null,
      };
    }
  }
}
