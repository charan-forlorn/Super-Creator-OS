/**
 * Phase 2 — typed client transport for the Brand Kit store.
 *
 * The browser is NEVER the authority: every read comes from the same-origin
 * authoritative API, every write is confirmed by the authoritative response.
 * No optimistic state; no browser storage; no demo fallback.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { BrandKit, TruthStatus } from "@/lib/brand-kit-store";

export type { BrandKit, TruthStatus } from "@/lib/brand-kit-store";

export interface BrandKitInput {
  name: string;
  colors: { primary: string; secondary: string; accent: string; neutrals: string[] };
  fonts: { heading: string; body: string };
  logo: { asset_ref: string; kind: "local-ref" };
  contact: { name: string; email: string; socials: { label: string; handle: string }[] };
  basic_cta: { label: string; target: string };
}

export interface WriteEnvelope {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  record: BrandKit | null;
}

export interface UseBrandKit {
  loadState: "loading" | "ready" | "error";
  truthStatus: TruthStatus | null;
  records: BrandKit[];
  errorCode: string | null;
  detail: string | null;
  refresh: () => void;
  save: (input: BrandKitInput) => Promise<WriteEnvelope>;
}

function parseWrite(data: unknown): WriteEnvelope {
  if (!data || typeof data !== "object") {
    return { ok: false, error_code: "RESPONSE_MALFORMED", detail: "no body", record: null };
  }
  const d = data as Record<string, unknown>;
  const record = (d.record ?? null) as BrandKit | null;
  return {
    ok: Boolean(d.ok),
    error_code: (d.error_code as string | null) ?? null,
    detail: (d.detail as string | null) ?? null,
    record: record && typeof record === "object" ? record : null,
  };
}

function parseRead(data: unknown): { status: TruthStatus; records: BrandKit[] } {
  if (!data || typeof data !== "object") {
    return { status: "UNAVAILABLE", records: [] };
  }
  const d = data as Record<string, unknown>;
  const recordsRaw = Array.isArray(d.records) ? d.records : [];
  const records = recordsRaw.filter(
    (r): r is BrandKit => !!r && typeof r === "object" && typeof (r as BrandKit).brand_kit_id === "string",
  );
  return { status: (d.status as TruthStatus) ?? "UNAVAILABLE", records };
}

export function useBrandKit(): UseBrandKit {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [truthStatus, setTruthStatus] = useState<TruthStatus | null>(null);
  const [records, setRecords] = useState<BrandKit[]>([]);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const requestSeq = useRef(0);

  const refresh = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoadState("loading");
    fetch("/api/brand-kit", { method: "GET", cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`http_${res.status}`);
        return res.json();
      })
      .then((payload: unknown) => {
        if (seq !== requestSeq.current) return;
        const env = parseRead(payload);
        setTruthStatus(env.status);
        setRecords(env.records);
        setErrorCode(null);
        setDetail(null);
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        setTruthStatus("UNAVAILABLE");
        setRecords([]);
        setErrorCode("READ_FAILED");
        setDetail(err instanceof Error ? err.message : "unknown_error");
        setLoadState("ready");
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const save = useCallback(
    async (input: BrandKitInput): Promise<WriteEnvelope> => {
      try {
        const res = await fetch("/api/brand-kit", {
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
    },
    [refresh],
  );

  return { loadState, truthStatus, records, errorCode, detail, refresh, save };
}
