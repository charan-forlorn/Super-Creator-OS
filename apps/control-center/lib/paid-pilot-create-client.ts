/** Browser client for canonical paid-pilot project creation (§6.E/§6.F bridge).

 *  The browser submits ONLY operation + idempotency key (server-generated).
 *  It never submits a filesystem path.
 */

export interface CreateCanonicalResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  canonical_internal_project_id: string | null;
  pilot_safe_id: string | null;
  project_safe_id: string | null;
  external_project_ref: string | null;
  admission_packet_sha256: string | null;
  replay: boolean | null;
  materialization: Record<string, unknown> | null;
  next_safe_action: string | null;
}

export async function createCanonicalProject(idempotencyKey: string): Promise<CreateCanonicalResponse> {
  const res = await fetch("/api/paid-pilot/create", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ operation: "create-canonical-project", idempotency_key: idempotencyKey }),
  });
  const data = (await res.json()) as CreateCanonicalResponse;
  return data;
}
