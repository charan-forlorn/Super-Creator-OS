/**
 * Cohort 10G — client-safe golden-render contract.
 *
 * NO node imports here on purpose: this module is imported by the operator
 * panel (a "use client" component), so it must not pull in node:child_process
 * (which webpack cannot bundle for the browser). The authoritative spawning
 * logic lives in ./golden-render-store (server-side only).
 */

export type GoldenRenderProfile = "vertical_9_16" | "square_1_1" | "landscape_16_9";

export type GoldenRenderOperation = "projection" | "execute" | "reconcile";

export interface GoldenRenderRequest {
  project_id: string;
  hvs_project_id: string;
  profile_id: GoldenRenderProfile;
  authorization_id: string;
  operator_id: string;
  store_path?: string;
  [key: string]: unknown;
}

export function serverResolvedScope(): { storePath?: string; hvsRepoPath?: string } {
  const storePath = process.env.SCOS_GOLDEN_RENDER_STORE_PATH;
  const hvsRepoPath = process.env.SCOS_HVS_REPO_PATH;
  return {
    storePath: storePath && storePath.length > 0 ? storePath : undefined,
    hvsRepoPath: hvsRepoPath && hvsRepoPath.length > 0 ? hvsRepoPath : undefined,
  };
}

export function buildExecutePayload(args: {
  projectId: string;
  hvsProjectId: string;
  profileId: GoldenRenderProfile;
  authorizationId: string;
  operatorId: string;
  storePath?: string;
}): GoldenRenderRequest {
  const req: GoldenRenderRequest = {
    project_id: args.projectId,
    hvs_project_id: args.hvsProjectId,
    profile_id: args.profileId,
    authorization_id: args.authorizationId,
    operator_id: args.operatorId,
  };
  if (args.storePath) req.store_path = args.storePath;
  return req;
}

const ALLOWED_FIELDS = new Set([
  "project_id",
  "hvs_project_id",
  "profile_id",
  "authorization_id",
  "operator_id",
  "store_path",
]);

/**
 * Server-side request validation contract (shared so the panel can preview
 * the same shape). Mirrors the Python bridge's field + pattern rules.
 */
export function validateGoldenRenderRequest(body: unknown): {
  ok: boolean;
  error_code: string | null;
  value: GoldenRenderRequest | null;
} {
  if (typeof body !== "object" || body === null) {
    return { ok: false, error_code: "REQUEST_MALFORMED", value: null };
  }
  const obj = body as Record<string, unknown>;
  const unexpected = Object.keys(obj).filter((k) => !ALLOWED_FIELDS.has(k));
  if (unexpected.length > 0) {
    return { ok: false, error_code: "REQUEST_UNEXPECTED_FIELD", value: null };
  }
  const required: [keyof GoldenRenderRequest, RegExp][] = [
    ["project_id", /^coh10g_[vsl]$/],
    ["hvs_project_id", /^[a-f0-9]{12}$/],
    ["profile_id", /^(vertical_9_16|square_1_1|landscape_16_9)$/],
    ["authorization_id", /^[a-z0-9_-]{2,64}$/],
    ["operator_id", /^[a-z0-9_-]{2,64}$/],
  ];
  for (const [field, pattern] of required) {
    const v = String(obj[field] ?? "");
    if (!v || !pattern.test(v)) {
      return { ok: false, error_code: "REQUEST_MALFORMED", value: null };
    }
  }
  return { ok: true, error_code: null, value: obj as GoldenRenderRequest };
}
