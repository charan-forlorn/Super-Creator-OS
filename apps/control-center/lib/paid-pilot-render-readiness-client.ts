/** Browser-side client for the pre-render readiness authority (§6.F).

 *  Read-only. The browser submits only the external project_ref. The server
 *  resolves canonical id + task-owned roots from environment. This client never
 *  sends a render request and never triggers a renderer.
 */

export interface ReadinessCheck {
  token: string;
  passed: boolean;
  reason_code: string;
  detail: string;
}
export interface ReadinessProjection {
  schema_version: string;
  canonical_internal_project_id: string;
  external_project_ref: string;
  output_profile: string | null;
  dimensions: string | null;
  duration_seconds: number | null;
  audio_duration_seconds: number | null;
  font_family: string | null;
  asset_safe_names: string[];
  render_action: string;
}
export interface RenderReadinessResponse {
  ok: boolean;
  state: string;
  error_code: string | null;
  detail: string | null;
  checks: ReadinessCheck[];
  projection: ReadinessProjection | null;
}

export async function evaluateRenderReadiness(externalProjectRef: string): Promise<RenderReadinessResponse> {
  try {
    const res = await fetch("/api/paid-pilot/render-readiness", {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ external_project_ref: externalProjectRef }),
    });
    const d = (await res.json()) as RenderReadinessResponse;
    return {
      ok: Boolean(d.ok),
      state: d.state ?? "NOT_READY",
      error_code: d.error_code ?? null,
      detail: d.detail ?? null,
      checks: d.checks ?? [],
      projection: d.projection ?? null,
    };
  } catch (e) {
    return { ok: false, state: "NOT_READY", error_code: "REQUEST_FAILED", detail: e instanceof Error ? e.message : "unknown", checks: [], projection: null };
  }
}
