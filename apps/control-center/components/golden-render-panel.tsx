"use client";

import { useState } from "react";

import {
  buildExecutePayload,
  type GoldenRenderProfile,
} from "@/lib/golden-render-contract";

interface GoldenRenderResult {
  state: string;
  attempt_id: string | null;
  artifact_id: string | null;
  artifact_checksum: string | null;
  render_calls: number;
  hvs_calls: number;
  qa_overall_state: string | null;
  qa_report_id: string | null;
  qa_failure_codes: string[];
  attempt: Record<string, unknown> | null;
  qa_report: Record<string, unknown> | null;
}

const PROFILES: { id: GoldenRenderProfile; label: string; dims: string }[] = [
  { id: "vertical_9_16", label: "Vertical", dims: "1080×1920" },
  { id: "square_1_1", label: "Square", dims: "1080×1080" },
  { id: "landscape_16_9", label: "Landscape", dims: "1920×1080" },
];

// Operator-reviewed mapping: each SCOS project -> HVS project id.
const PROJECT_MAP: Record<GoldenRenderProfile, { projectId: string; hvsProjectId: string }> = {
  vertical_9_16: { projectId: "coh10g_v", hvsProjectId: "451424382c69" },
  square_1_1: { projectId: "coh10g_s", hvsProjectId: "e415843f887e" },
  landscape_16_9: { projectId: "coh10g_l", hvsProjectId: "a8082bc56006" },
};

function toneFor(state: string | null): string {
  if (state === "RENDER_SUCCEEDED") return "text-status-review";
  if (state === "RENDER_FAILED_CONFIRMED") return "text-status-failed";
  if (state === "QA_PASSED") return "text-status-review";
  if (state?.startsWith("QA_")) return "text-status-waiting";
  return "text-status-waiting";
}

export function GoldenRenderPanel() {
  const [operatorId, setOperatorId] = useState("local-solo-operator");
  const [pending, setPending] = useState<GoldenRenderProfile | null>(null);
  const [results, setResults] = useState<Record<string, GoldenRenderResult>>({});
  const [error, setError] = useState<string | null>(null);

  async function execute(profile: GoldenRenderProfile) {
    if (pending) return;
    setPending(profile);
    setError(null);
    const map = PROJECT_MAP[profile];
    const authId = `az_${profile.slice(0, 1)}_001`;
    try {
      const res = await fetch("/api/golden-render/execute", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(
          buildExecutePayload({
            projectId: map.projectId,
            hvsProjectId: map.hvsProjectId,
            profileId: profile,
            authorizationId: authId,
            operatorId: operatorId || "local-solo-operator",
          }),
        ),
      });
      const data = (await res.json()) as { ok: boolean; error_code?: string | null; result?: GoldenRenderResult };
      if (!data.ok || !data.result) {
        setError(data.error_code ?? "EXECUTION_FAILED");
        return;
      }
      setResults((prev) => ({ ...prev, [profile]: data.result as GoldenRenderResult }));
    } catch {
      setError("BACKEND_ROUTE_UNAVAILABLE");
    } finally {
      setPending(null);
    }
  }

  return (
    <section
      className="rounded-card border border-border bg-surface p-4"
      aria-labelledby="golden-render-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="golden-render-title" className="text-sm font-semibold">
            Cohort 10G — Golden Render Matrix
          </h2>
          <p className="text-xs text-muted-foreground">
            Operator-authorized real HVS render. One real render per profile. No terminal required.
          </p>
        </div>
        <label className="text-xs text-muted-foreground">
          Operator
          <input
            className="ml-2 rounded border border-border-soft bg-background px-2 py-1 text-xs"
            value={operatorId}
            onChange={(e) => setOperatorId(e.target.value)}
            aria-label="operator id"
          />
        </label>
      </div>

      {error && (
        <p className="mt-2 rounded border border-status-failed/40 bg-status-failed/10 px-2 py-1 text-xs text-status-failed">
          Error: {error}
        </p>
      )}

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        {PROFILES.map((p) => {
          const r = results[p.id];
          const busy = pending === p.id;
          return (
            <div key={p.id} className="rounded border border-border-soft bg-background p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{p.label}</span>
                <span className="text-[10px] text-muted-foreground">{p.dims}</span>
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {p.id}
              </div>
              <button
                type="button"
                className="mt-2 w-full rounded bg-primary px-2 py-1 text-xs font-semibold text-primary-foreground disabled:opacity-50"
                onClick={() => execute(p.id)}
                disabled={busy || pending !== null}
                aria-label={`execute ${p.label} render`}
              >
                {busy ? "Rendering…" : "Render (operator-authorized)"}
              </button>
              {r && (
                <div className="mt-2 text-[11px]">
                  <div>
                    State:{" "}
                    <span className={toneFor(r.state)}>{r.state}</span>
                  </div>
                  <div>
                    QA:{" "}
                    <span className={toneFor(r.qa_overall_state)}>
                      {r.qa_overall_state ?? "—"}
                    </span>
                  </div>
                  {r.artifact_checksum && (
                    <div className="truncate text-muted-foreground">
                      sha256: {r.artifact_checksum.slice(0, 16)}…
                    </div>
                  )}
                  {r.qa_failure_codes?.length ? (
                    <div className="text-status-failed">
                      warns: {r.qa_failure_codes.join(", ")}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
