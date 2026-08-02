/** Browser client for the packet-admission authority (§6.A).

 *  The browser submits ONLY operation + expected_sha256 (operator seal). It
 *  never submits a filesystem path. All roots are resolved server-side.
 */

export interface AdmissionProjection {
  packet_sha256?: string;
  pilot_id?: string;
  customer_ref?: string;
  project_ref?: string;
  output_profile?: string;
  duration?: number | string;
  title?: string;
  asset_count?: number;
  assets?: Array<Record<string, unknown>>;
  external_action_restrictions?: Record<string, string>;
  delivery_method?: string;
  font_policy?: string;
}

export interface AdmissionResponse {
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  gates?: Array<{ token: string; passed: boolean; reason_code: string; detail: string }>;
  assets?: Array<Record<string, unknown>>;
  projection: AdmissionProjection | null;
}

export async function admitRealPacket(expectedSha256: string): Promise<AdmissionResponse> {
  const res = await fetch("/api/paid-pilot/admission", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ operation: "admit-packet", expected_sha256: expectedSha256 }),
  });
  const data = (await res.json()) as Omit<AdmissionResponse, "ok" | "error_code" | "detail"> & {
    ok: boolean;
    error_code: string | null;
    detail: string | null;
  };
  return {
    ok: data.ok,
    error_code: data.error_code,
    detail: data.detail,
    gates: data.gates,
    assets: data.assets,
    projection: data.projection,
  };
}
