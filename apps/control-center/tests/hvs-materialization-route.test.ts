import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { rmSync, existsSync } from "node:fs";

import { POST as authorizePost } from "@/app/api/hvs-materialization/authorize/route";
import { POST as executePost } from "@/app/api/hvs-materialization/execute/route";
import { POST as reconcilePost } from "@/app/api/hvs-materialization/reconcile/route";
import { GET as projectionGet } from "@/app/api/hvs-materialization/projection/route";
import {
  hvsMaterializationStorePath,
  hvsMaterializationDestinationRoot,
} from "@/lib/hvs-materialization-store";

const PROJECT = "spp-25177649af09";

function cleanup() {
  for (const p of [hvsMaterializationStorePath(), `${hvsMaterializationStorePath()}.lock`, `${hvsMaterializationStorePath()}.integrity.json`]) {
    try {
      if (existsSync(p)) rmSync(p, { force: true });
    } catch {
      /* ignore */
    }
  }
  try {
    if (existsSync(hvsMaterializationDestinationRoot())) rmSync(hvsMaterializationDestinationRoot(), { recursive: true, force: true });
  } catch {
    /* ignore */
  }
}

beforeEach(() => cleanup());
afterEach(() => cleanup());

function post(url: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${url}`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

describe("Cohort 10D materialization routes — authorization gating", () => {
  it("denies authorization when confirmation is not explicit (req 3)", async () => {
    const res = await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: false, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.ok).toBe(false);
    expect(body.decision).toBe("DENIED");
  });

  it("issues an AUTHORIZED decision only on explicit confirmation", async () => {
    const res = await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.decision).toBe("AUTHORIZED");
    expect(body.authorization.destination_identity).toContain("hvs-projects");
    expect(body.authorization.destination_identity).not.toContain("database.json");
    expect(body.authorization.materialization_plan_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("rejects malformed project ids with no stack trace", async () => {
    const res = await authorizePost(post("/api/hvs-materialization/authorize", { projectId: "../evil", projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0" }));
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.error_code).toBe("PROJECT_NOT_FOUND");
    expect(JSON.stringify(body)).not.toMatch(/at\s+\w|Error:|stack/i);
  });
});

describe("Cohort 10D materialization routes — single HVS call + replay", () => {
  it("execute invokes HVS exactly once and exact replay causes no second call (req 5/8)", async () => {
    await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    const first = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 2, authorizationId: "auth-1", capabilityId: "cap-1", attemptId: "att-1", operatorId: "op" }));
    expect(first.status).toBe(200);
    const firstBody = await first.json();
    expect(firstBody.ok).toBe(true);
    expect(firstBody.result.hvs_calls).toBe(1);

    const replay = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 2, authorizationId: "auth-1", capabilityId: "cap-1", attemptId: "att-replay", operatorId: "op" }));
    const replayBody = await replay.json();
    expect(replayBody.ok).toBe(false);
    expect(replayBody.result.hvs_calls).toBe(0);
    expect(replayBody.error_code).toBe("CAPABILITY_CONSUMED");
  });

  it("revision conflict is shown truthfully (req 11)", async () => {
    await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    const res = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 3, authorizationId: "auth-1", capabilityId: "cap-1", attemptId: "att-1", operatorId: "op" }));
    const body = await res.json();
    expect(body.ok).toBe(false);
    expect(body.error_code).toBe("AUTHORIZATION_REVISION_MISMATCH");
  });

  it("a corrupt store yields a masked detail with no absolute path leak (req 13)", async () => {
    const fs = await import("node:fs");
    fs.writeFileSync(hvsMaterializationStorePath(), "{not json", "utf8");
    const res = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 2, authorizationId: "auth-x", capabilityId: "cap-x", attemptId: "att-x", operatorId: "op" }));
    expect(res.status).toBe(409);
    const body = await res.json();
    // A corrupt store is fail-closed (STORE_CORRUPT) and the detail never
    // leaks the absolute filesystem path or raw error text.
    expect(body.error_code).toBe("STORE_CORRUPT");
    expect(body.detail).toBe("malformed store");
    expect(JSON.stringify(body)).not.toMatch(/[A-Z]:\\|integrity|\.json\.lock|calibri/i);
  });
});

describe("Cohort 10D materialization routes — projection + reconciliation", () => {
  it("projection is read-only and surfaces a deterministic plan before authorization (req 1)", async () => {
    const res = await projectionGet(new NextRequest(`http://localhost/api/hvs-materialization/projection?projectId=${PROJECT}`, { method: "GET" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.projection.truth_state).toBe("MATERIALIZATION_NOT_REQUESTED");
    expect(body.projection.plan.plan_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("reconciliation is read-only and classifies an unknown attempt without retrying (req 9/10)", async () => {
    const fs = await import("node:fs");
    fs.writeFileSync(
      hvsMaterializationStorePath(),
      JSON.stringify({
        schema_version: 1,
        store_kind: "scos.hvs_project_materialization.v1",
        written_at: "2026-07-17T00:00:00.000Z",
        authorizations: {},
        capabilities: {},
        attempts: {
          "att-u": {
            attempt_id: "att-u",
            project_id: PROJECT,
            project_revision: 2,
            plan_hash: "0".repeat(64),
            destination_identity: hvsMaterializationDestinationRoot(),
            authorization_id: "auth-1",
            capability_id: "cap-1",
            state: "MATERIALIZATION_OUTCOME_UNKNOWN",
            hvs_calls: 1,
            started_at: "2026-07-17T00:00:00.000Z",
            finished_at: "2026-07-17T00:00:01.000Z",
            outcome: "unknown",
            error_code: "HVS_INIT_FAILED",
            error_detail: "timeout",
            persisted_result: null,
          },
        },
      }),
      "utf8",
    );
    const res = await reconcilePost(post("/api/hvs-materialization/reconcile", { attemptId: "att-u" }));
    const body = await res.json();
    // Read-only reconciliation of an unknown attempt whose project is absent
    // at the destination: classified (not retried), and the HVS call count is
    // unchanged (no new HVS mutation).
    expect(body.ok).toBe(false);
    expect(body.classification).toBe("CONFIRMED_NOT_MATERIALIZED");
    expect(body.attempt.hvs_calls).toBe(1); // unchanged: read-only
    expect(["MATERIALIZATION_RECONCILIATION_REQUIRED", "MATERIALIZATION_OUTCOME_UNKNOWN"]).toContain(body.attempt.state);
  });
});
