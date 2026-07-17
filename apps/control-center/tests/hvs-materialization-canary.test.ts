/**
 * Cohort 10D — isolated local-first canary.
 *
 * Exercises the controlled HVS materialization boundary end-to-end against the
 * REAL Python CLI bridge with a FRESH, ISOLATED OS-temp store + the
 * bridge's own isolated projects_root. Mirrors the "isolated real-HVS
 * canary" requirement: isolated temp HVS root, max 1 HVS-boundary call,
 * render/FFmpeg/FFprobe/Chromium/HyperFrames/external = 0, no retry on
 * unknown. The SOLE real HVS mutation boundary is the existing
 * HermesVideoStudioAdapter reached through the Python service (the bridge),
 * NOT a TypeScript double. The real HVS repo is never touched.
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
    // The authoritative store resolves store_path as a DIRECTORY and appends
    // its canonical envelope file; pass the directory, not a file.
    storePath: root,
    dest: join(root, "projects"),
  };
}

describe("Cohort 10D canary — controlled materialization in isolation", () => {
  const dirs: string[] = [];

  afterEach(() => {
    for (const d of dirs) rmSync(d, { recursive: true, force: true });
    dirs.length = 0;
  });

  it("materializes exactly once through the real bridge; replay is contained; reconcile is read-only (req 5/8/9/10)", async () => {
    const { root, storePath, dest } = freshRoots();
    dirs.push(root);
    const store = new HvsMaterializationStore();

    // 1) Authorize on explicit confirmation (real Python authority).
    const auth = await store.invoke("authorize",
      { project_id: PROJECT, project_revision: 2, confirmed: true, authorization_id: "auth-1", nonce: "n0", operator_id: "op", store_path: storePath });
    expect(auth.ok).toBe(true);
    expect(auth.response?.decision).toBe("AUTHORIZED");

    // 2) Execute — exactly ONE HVS-boundary call through the bridge.
    const res = await store.invoke("execute",
      { project_id: PROJECT, project_revision: 2, authorization_id: "auth-1", capability_id: "cap-1", attempt_id: "att-1", operator_id: "op", store_path: storePath, projects_root: dest });
    expect(res.ok).toBe(true);
    expect(res.response?.ok).toBe(true);
    expect(res.response?.hvs_calls).toBe(1); // <= 1 HVS boundary call
    expect(res.response?.state).toBe("HVS_PROJECT_MATERIALIZED");

    // The real HVS CLI materialized the project structure under the
    // isolated destination (the bridge's own isolated projects_root),
    // and NOTHING render/ffmpeg/chromium/hyperframes.
    // The authoritative store materializes the HVS project directly under
    // projects_root as <hvs_project_name> (e.g. projects_root/hvs-<id>).
    const projectDir = join(dest, "hvs-25177649af09");
    expect(existsSync(projectDir)).toBe(true);
    const files = readdirSync(projectDir);
    expect(files).toContain("initialization_manifest.json");
    expect(files).toContain("project_brief.json");
    expect(files.some((f) => /render|ffmpeg|ffprobe|chromium|hyperframes/i.test(f))).toBe(false);

    // 3) Exact replay — contained, ZERO additional HVS calls.
    const replay = await store.invoke("execute",
      { project_id: PROJECT, project_revision: 2, authorization_id: "auth-1", capability_id: "cap-1", attempt_id: "att-replay", operator_id: "op", store_path: storePath, projects_root: dest });
    expect(replay.ok).toBe(true);
    expect(replay.response?.ok).toBe(false);
    expect(replay.response?.error_code).toBe("CAPABILITY_CONSUMED");
    expect(replay.response?.hvs_calls ?? 0).toBe(0);

    // 4) Read-only reconciliation of the materialized attempt.
    // Pass the SAME isolated projects_root the execute materialized into, so
    // the inspector re-reads the authoritative isolated project (never the
    // invalid default hvs_repo_path fallback).
    const rec = await store.invoke("reconcile", { attempt_id: "att-1", store_path: storePath, projects_root: dest });
    expect(rec.ok).toBe(true);
    expect(rec.response?.classification).toBe("HVS_PROJECT_MATERIALIZED");
    expect(rec.response?.attempt?.hvs_calls).toBe(1); // unchanged: read-only
  });

  it("rejects an arbitrary/forbidden destination (no production HVS target)", async () => {
    const { root, storePath, dest } = freshRoots();
    dirs.push(root);
    const store = new HvsMaterializationStore();
    const auth = await store.invoke("authorize",
      { project_id: PROJECT, project_revision: 2, confirmed: true, authorization_id: "auth-1", nonce: "n0", operator_id: "op", store_path: storePath });
    expect(auth.ok).toBe(true);
    // The browser/TScript layer cannot supply a destination; the Python
    // authority enforces the isolated destination. We assert the bridge
    // never materializes into a forbidden production root by confirming the
    // authoritative store rejects a mismatched destination identity.
    const res = await store.invoke("execute",
      { project_id: PROJECT, project_revision: 2, authorization_id: "auth-1", capability_id: "cap-1", attempt_id: "att-1", operator_id: "op", store_path: storePath, projects_root: dest, destination_identity: "C:/Workspace/hermes-video-studio/projects" });
    expect(res.ok).toBe(true);
    expect(res.response?.ok).toBe(false);
    // The authority rejects a non-isolated destination; it surfaces the
    // plan mismatch (the destination is part of the authorized plan hash).
    expect(res.response?.error_code).toBe("AUTHORIZATION_PLAN_MISMATCH");
    expect(res.response?.hvs_calls ?? 0).toBe(0);
  });
});
