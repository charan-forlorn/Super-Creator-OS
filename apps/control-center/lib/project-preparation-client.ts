/**
 * Cohort 10C — typed client transport for the authoritative project-
 * preparation store.
 *
 * The browser is NEVER the authority (Cohort 10C §3): every read
 * comes from the same-origin authorative API, and every transition is
 * confirmed by the authorative response before the UI advances. No
 * optimistic state advancement; no browser storage; no demo fallback.
 *
 * Truth states the UI must render explicitly:
 *  AVAILABLE_WITH_DATA | EMPTY | UNAVAILABLE | CORRUPT | INCOMPATIBLE_SCHEMA
 */

import { useCallback, useEffect, useRef, useState } from "react";

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

export interface SideEffectFlags {
  side_effects_performed: false;
  render_started: false;
  hvs_project_created: false;
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
  side_effect_flags: SideEffectFlags;
}

export interface ReadEnvelope {
  status: TruthStatus;
  schema_version: number;
  error_code: string | null;
  detail: string | null;
  records: ProjectPreparationRecord[];
}

export interface WriteEnvelope {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: ProjectPreparationRecord | null;
}

export interface UseProjectPreparation {
  loadState: "loading" | "ready" | "error";
  truthStatus: TruthStatus | null;
  records: ProjectPreparationRecord[];
  errorCode: string | null;
  detail: string | null;
  observedAt: string | null;
  refresh: () => void;
  createDraft: (input: ProjectDraftInput) => Promise<WriteEnvelope>;
  approve: (projectId: string, expectedRevision: number) => Promise<WriteEnvelope>;
  createPreview: (projectId: string, expectedRevision: number) => Promise<WriteEnvelope>;
}

export interface ProjectDraftInput {
  projectTitle: string;
  clientOrBrand: string;
  projectPurpose: string;
  contentBrief: string;
  targetDurationSeconds: number;
  outputProfiles: string[];
  operatorNotes: string;
}

const SAFE_ID_PATTERN = /^spp-[a-f0-9]{12}$/;

function parseWrite(data: unknown): WriteEnvelope {
  if (!data || typeof data !== "object") {
    return { ok: false, error_code: "RESPONSE_MALFORMED", detail: "no body", record: null };
  }
  const d = data as Record<string, unknown>;
  const record = (d.record ?? null) as ProjectPreparationRecord | null;
  return {
    ok: Boolean(d.ok),
    error_code: (d.error_code as string | null) ?? null,
    detail: (d.detail as string | null) ?? null,
    record: record && typeof record === "object" ? record : null,
  };
}

function parseRead(data: unknown): ReadEnvelope {
  if (!data || typeof data !== "object") {
    return {
      status: "UNAVAILABLE",
      schema_version: 1,
      error_code: "RESPONSE_MALFORMED",
      detail: "no body",
      records: [],
    };
  }
  const d = data as Record<string, unknown>;
  const status = (d.status as TruthStatus) ?? "UNAVAILABLE";
  const recordsRaw = Array.isArray(d.records) ? d.records : [];
  const records = recordsRaw.filter(
    (r): r is ProjectPreparationRecord =>
      !!r && typeof r === "object" && SAFE_ID_PATTERN.test(String((r as ProjectPreparationRecord).project_id)),
  );
  return {
    status,
    schema_version: (d.schema_version as number) ?? 1,
    error_code: (d.error_code as string | null) ?? null,
    detail: (d.detail as string | null) ?? null,
    records,
  };
}

export function useProjectPreparation(): UseProjectPreparation {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [truthStatus, setTruthStatus] = useState<TruthStatus | null>(null);
  const [records, setRecords] = useState<ProjectPreparationRecord[]>([]);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoadState("loading");
    fetch("/api/project-preparation", { method: "GET", cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`http_${res.status}`);
        return res.json();
      })
      .then((payload: unknown) => {
        if (seq !== requestSeq.current) return;
        const env = parseRead(payload);
        setTruthStatus(env.status);
        setRecords(env.records);
        setErrorCode(env.error_code);
        setDetail(env.detail);
        setObservedAt(new Date().toISOString());
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        // Fail closed: represent unavailability, never empty/fabricated.
        setTruthStatus("UNAVAILABLE");
        setRecords([]);
        setErrorCode("READ_FAILED");
        setDetail(err instanceof Error ? err.message : "unknown_error");
        setObservedAt(new Date().toISOString());
        setLoadState("ready");
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createDraft = useCallback(async (input: ProjectDraftInput): Promise<WriteEnvelope> => {
    try {
      const res = await fetch("/api/project-preparation", {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(input),
      });
      const data = await res.json();
      const env = parseWrite(data);
      if (env.ok) refresh();
      return env;
    } catch (err: unknown) {
      return {
        ok: false,
        error_code: "REQUEST_FAILED",
        detail: err instanceof Error ? err.message : "unknown_error",
        record: null,
      };
    }
  }, [refresh]);

  const approve = useCallback(async (projectId: string, expectedRevision: number): Promise<WriteEnvelope> => {
    if (!SAFE_ID_PATTERN.test(projectId)) {
      return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id", record: null };
    }
    try {
      const res = await fetch(`/api/project-preparation/${projectId}/approve`, {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expectedRevision }),
      });
      const data = await res.json();
      const env = parseWrite(data);
      if (env.ok) refresh();
      return env;
    } catch (err: unknown) {
      return {
        ok: false,
        error_code: "REQUEST_FAILED",
        detail: err instanceof Error ? err.message : "unknown_error",
        record: null,
      };
    }
  }, [refresh]);

  const createPreview = useCallback(async (projectId: string, expectedRevision: number): Promise<WriteEnvelope> => {
    if (!SAFE_ID_PATTERN.test(projectId)) {
      return { ok: false, error_code: "PROJECT_NOT_FOUND", detail: "malformed project_id", record: null };
    }
    try {
      const res = await fetch(`/api/project-preparation/${projectId}/preview`, {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expectedRevision }),
      });
      const data = await res.json();
      const env = parseWrite(data);
      if (env.ok) refresh();
      return env;
    } catch (err: unknown) {
      return {
        ok: false,
        error_code: "REQUEST_FAILED",
        detail: err instanceof Error ? err.message : "unknown_error",
        record: null,
      };
    }
  }, [refresh]);

  return {
    loadState,
    truthStatus,
    records,
    errorCode,
    detail,
    observedAt,
    refresh,
    createDraft,
    approve,
    createPreview,
  };
}
