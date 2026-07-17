import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

import { POST as authorizePost } from "@/app/api/hvs-materialization/authorize/route";
import { POST as executePost } from "@/app/api/hvs-materialization/execute/route";
import { POST as reconcilePost } from "@/app/api/hvs-materialization/reconcile/route";
import { GET as projectionGet } from "@/app/api/hvs-materialization/projection/route";

const PROJECT = "spp-25177649af09";

// Each test gets FRESH, ISOLATED OS-temp stores via trusted server-side env
// overrides (never browser-supplied). This prevents state leaking between
// tests and avoids touching the shared default store.
let storePath: string;
let projectsRoot: string;
let prevStore: string | undefined;
let prevRoot: string | undefined;

function post(url: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${url}`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  storePath = mkdtempSync(resolve(tmpdir(), "hvs-route-store-"));
  projectsRoot = mkdtempSync(resolve(tmpdir(), "hvs-route-root-"));
  prevStore = process.env.SCOS_HVS_STORE_PATH;
  prevRoot = process.env.SCOS_HVS_PROJECTS_ROOT;
  process.env.SCOS_HVS_STORE_PATH = storePath;
  process.env.SCOS_HVS_PROJECTS_ROOT = projectsRoot;
});

afterEach(() => {
  if (prevStore === undefined) delete process.env.SCOS_HVS_STORE_PATH;
  else process.env.SCOS_HVS_STORE_PATH = prevStore;
  if (prevRoot === undefined) delete process.env.SCOS_HVS_PROJECTS_ROOT;
  else process.env.SCOS_HVS_PROJECTS_ROOT = prevRoot;
  try { rmSync(storePath, { recursive: true, force: true }); } catch { /* ignore */ }
  try { rmSync(projectsRoot, { recursive: true, force: true }); } catch { /* ignore */ }
});

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
    expect(body.authorization.materialization_plan_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("rejects malformed project ids with no stack trace", async () => {
    const res = await authorizePost(post("/api/hvs-materialization/authorize", { projectId: "../evil", projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0" }));
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.error_code).toBe("PROJECT_NOT_FOUND");
    expect(JSON.stringify(body)).not.toMatch(/at\s+\w|Error:|stack/i);
  });

  it("rejects unexpected fields (no arbitrary path input)", async () => {
    const res = await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", evilPath: "C:/Workspace/hermes-video-studio" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error_code).toBe("REQUEST_UNEXPECTED_FIELD");
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
    expect(replayBody.ok).toBe(true);
    expect(replayBody.result.ok).toBe(false);
    expect(replayBody.result.hvs_calls).toBe(0);
    expect(replayBody.result.error_code).toBe("CAPABILITY_CONSUMED");
  });

  it("revision conflict is shown truthfully (req 11)", async () => {
    await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    const res = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 3, authorizationId: "auth-1", capabilityId: "cap-1", attemptId: "att-1", operatorId: "op" }));
    const body = await res.json();
    // Transport ok; authority verdict is in result.
    expect(body.ok).toBe(true);
    expect(body.result.ok).toBe(false);
    expect(body.result.error_code).toBe("AUTHORIZATION_REVISION_MISMATCH");
  });
});

describe("Cohort 10D materialization routes — projection + reconciliation", () => {
  it("projection is read-only and surfaces a deterministic plan before authorization (req 1)", async () => {
    // Projection needs an existing projection view; authorize first so the
    // truth state is MATERIALIZATION_NOT_REQUESTED (requested but not run).
    await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    const res = await projectionGet(new NextRequest(`http://localhost/api/hvs-materialization/projection?projectId=${PROJECT}`, { method: "GET" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(body.projection.truth_state).toBe("MATERIALIZATION_NOT_REQUESTED");
    expect(body.projection.plan.plan_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("reconciliation is read-only and classifies without retrying (req 9/10)", async () => {
    // Authorize + execute to create a materialized attempt, then reconcile.
    await authorizePost(post("/api/hvs-materialization/authorize", { projectId: PROJECT, projectRevision: 2, confirmed: true, authorizationId: "auth-1", nonce: "n0", operatorId: "op" }));
    const ex = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 2, authorizationId: "auth-1", capabilityId: "cap-1", attemptId: "att-1", operatorId: "op" }));
    expect((await ex.json()).ok).toBe(true);
    const rec = await reconcilePost(post("/api/hvs-materialization/reconcile", { attemptId: "att-1" }));
    const body = await rec.json();
    expect(body.ok).toBe(true);
    expect(body.classification).toBe("HVS_PROJECT_MATERIALIZED");
    // Read-only: no new HVS call happened during reconcile (hvs_calls unchanged).
    expect(body.attempt.hvs_calls).toBe(1);
  });
});

describe("Cohort 10D materialization routes — bridge fail closed", () => {
  it("a bridge failure is masked with no absolute path leak (req 13)", async () => {
    // Force the bridge to fail by pointing the trusted server-side interpreter
    // override at a non-existent binary (browser cannot set this).
    const prevPy = process.env.SCOS_PYTHON_INTERPRETER;
    process.env.SCOS_PYTHON_INTERPRETER = "C:/nonexistent/python.exe";
    try {
      const res = await executePost(post("/api/hvs-materialization/execute", { projectId: PROJECT, projectRevision: 2, authorizationId: "auth-x", capabilityId: "cap-x", attemptId: "att-x", operatorId: "op" }));
      expect(res.status).toBe(409);
      const body = await res.json();
      expect(body.ok).toBe(false);
      expect(body.result.error_detail).toBeNull();
      expect(JSON.stringify(body)).not.toMatch(/[A-Z]:\\|integrity|\.json\.lock|calibri/i);
    } finally {
      if (prevPy === undefined) delete process.env.SCOS_PYTHON_INTERPRETER;
      else process.env.SCOS_PYTHON_INTERPRETER = prevPy;
    }
  });
});
