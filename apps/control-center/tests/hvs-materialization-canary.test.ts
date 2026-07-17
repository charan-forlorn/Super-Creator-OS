/**
 * Cohort 10D — isolated local-first canary.
 *
 * Exercises the controlled HVS materialization boundary end-to-end against a
 * FRESH, ISOLATED OS-temp store + destination root (mirrors the "isolated
 * real-HVS canary" requirement: isolated temp HVS root, max 1 HVS-boundary
 * call, render/FFmpeg/FFprobe/Chromium/HyperFrames/external = 0, no retry on
 * unknown). The store's local HVS double is the sole HVS mutation boundary in
 * local-first mode; it performs exactly one controlled fs mutation and writes
 * no render/ffmpeg artifacts. The real HVS repo is never touched.
 */
import { describe, expect, it, afterEach } from "vitest";
import { mkdtempSync, rmSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { HvsMaterializationStore } from "@/lib/hvs-materialization-store";

const PROJECT = "spp-25177649af09";

const normalized = {
  project_title: "Canary Project",
  client_or_brand: "Canary Brand",
  project_purpose: "Local-first isolated canary",
  normalized_brief_summary: "No external egress; controlled boundary only.",
  target_duration_seconds: 45,
  output_profiles: [{ id: "vertical_9_16", label: "a", aspectRatio: "9:16" }],
  planned_rendition_count: 1,
  operator_notes: "",
};

function freshRoots() {
  const root = mkdtempSync(join(tmpdir(), "cohort10d-canary-"));
  return {
    root,
    storePath: join(root, "store.json"),
    dest: join(root, "projects"),
  };
}

describe("Cohort 10D canary — controlled materialization in isolation", () => {
  const dirs: string[] = [];

  afterEach(() => {
    for (const d of dirs) rmSync(d, { recursive: true, force: true });
    dirs.length = 0;
  });

  it("materializes exactly once through the controlled boundary; replay is contained; unknown is reconciled (req 5/8/9/10)", () => {
    const { root, storePath, dest } = freshRoots();
    dirs.push(root);
    const store = new HvsMaterializationStore(storePath, dest);

    // 1) Authorize on explicit confirmation.
    const auth = store.requestAuthorization({
      projectId: PROJECT,
      projectRevision: 2,
      normalized,
      confirmed: true,
      authorizationId: "auth-1",
      nonce: "n0",
      operatorId: "op",
    });
    expect(auth.decision).toBe("AUTHORIZED");
    expect(auth.error_code).toBeNull();
    expect(store.getAuthorization("auth-1")).not.toBeNull();

    // 2) Execute — exactly ONE HVS-boundary call.
    const res = store.executeMaterialization({
      projectId: PROJECT,
      projectRevision: 2,
      normalized,
      authorization: store.getAuthorization("auth-1"),
      capabilityId: "cap-1",
      attemptId: "att-1",
      operatorId: "op",
    });
    expect(res.ok).toBe(true);
    expect(res.result?.ok).toBe(true);
    expect(res.result?.hvsCalls).toBe(1); // <= 1 HVS boundary call
    expect(res.result?.state).toBe("HVS_PROJECT_MATERIALIZED");

    // The controlled boundary wrote the HVS project structure under the
    // isolated destination, and NOTHING render/ffmpeg/chromium/hyperframes.
    const projectDir = join(dest, "projects", "hvs-25177649af09");
    expect(existsSync(projectDir)).toBe(true);
    const files = readdirSync(projectDir);
    expect(files).toContain("initialization_manifest.json");
    expect(files).toContain("project_brief.json");
    // No forbidden render artifacts.
    expect(files.some((f) => /render|ffmpeg|ffprobe|chromium|hyperframes/i.test(f))).toBe(false);
    // Authoritative identity persisted (on the attempt record, not the result shape).
    expect((res.record as { persisted_result: { hvs_project_name: string } } | null)?.persisted_result?.hvs_project_name).toBe("hvs-25177649af09");

    // 3) Exact replay — contained, ZERO additional HVS calls.
    const replay = store.executeMaterialization({
      projectId: PROJECT,
      projectRevision: 2,
      normalized,
      authorization: store.getAuthorization("auth-1"),
      capabilityId: "cap-1",
      attemptId: "att-replay",
      operatorId: "op",
    });
    expect(replay.ok).toBe(false);
    expect(replay.error_code).toBe("CAPABILITY_CONSUMED");
    expect(replay.result?.hvsCalls ?? 0).toBe(0);

    // 4) Unknown outcome + read-only reconciliation (no retry / no new HVS call).
    const env = {
      schema_version: 1,
      store_kind: "scos.hvs_project_materialization.v1",
      written_at: "2026-07-17T00:00:00.000Z",
      authorizations: { "auth-1": store.getAuthorization("auth-1") },
      capabilities: {},
      attempts: {
        "att-u": {
          attempt_id: "att-u",
          project_id: PROJECT,
          project_revision: 2,
          plan_hash: "0".repeat(64),
          destination_identity: dest,
          authorization_id: "auth-1",
          capability_id: "cap-2",
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
    };
    const fs = require("node:fs");
    fs.writeFileSync(storePath, JSON.stringify(env, null, 2), "utf8");

    const rec = store.reconcile({ attemptId: "att-u" });
    expect(rec.ok).toBe(false); // unknown + absent project => not materialized, requires operator action
    expect(rec.classification).toBe("CORRUPT_MATERIALIZATION");
    expect((rec.record as { hvs_calls: number }).hvs_calls).toBe(1); // unchanged: read-only
  });

  it("rejects an arbitrary/forbidden destination (no production HVS target)", () => {
    const { root, storePath, dest } = freshRoots();
    dirs.push(root);
    const store = new HvsMaterializationStore(storePath, dest);
    store.requestAuthorization({
      projectId: PROJECT,
      projectRevision: 2,
      normalized,
      confirmed: true,
      authorizationId: "auth-1",
      nonce: "n0",
      operatorId: "op",
    });
    const res = store.executeMaterialization({
      projectId: PROJECT,
      projectRevision: 2,
      normalized,
      authorization: store.getAuthorization("auth-1"),
      capabilityId: "cap-1",
      attemptId: "att-1",
      operatorId: "op",
      destinationIdentity: "C:/Workspace/hermes-video-studio/projects",
    });
    expect(res.ok).toBe(false);
    expect(res.error_code).toBe("AUTHORIZATION_DESTINATION_MISMATCH");
    expect(res.result?.hvsCalls ?? 0).toBe(0);
  });
});
