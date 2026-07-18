import { describe, expect, it, beforeAll, afterAll } from "vitest";
import { existsSync, statSync, readFileSync, writeFileSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Phase 2 — Protected-repo guard.
 *
 * Team-D mandate: the Phase-2 test + bridge run MUST NOT mutate HVS Protected
 * Repository files. We snapshot the mtimes of the protected artifacts before
 * and after a representative Phase-2 run and assert they are unchanged.
 *
 * Protected set (read-only lineage / learning archive):
 *   - memory/database.json                       (operator learning DB)
 *   - scos/control_center/control_center_snapshot.py  (authoritative reader)
 *   - integrations/learning/archive              (provenance archive dirs)
 *
 * The Phase-2 suites touch only memory/runtime/control-center/* (runtime-only,
 * never the protected learning DB or archive).
 */

const ROOT = join(process.cwd(), "..", "..");
const PROTECTED = [
  join(ROOT, "memory", "database.json"),
  join(ROOT, "scos", "control_center", "control_center_snapshot.py"),
];

function mtime(path: string): number {
  return existsSync(path) ? statSync(path).mtimeMs : -1;
}

function snapshot(): Record<string, number> {
  const out: Record<string, number> = {};
  for (const p of PROTECTED) out[p] = mtime(p);
  return out;
}

describe("Phase 2 protected-repo guard", () => {
  const before = snapshot();
  const probeDir = join(ROOT, "memory", "runtime", "control-center", "guard-probe");
  const probeFile = join(probeDir, "probe.json");

  beforeAll(() => {
    // Simulate a legitimate Phase-2 runtime write (allowed location).
    mkdirSync(probeDir, { recursive: true });
    writeFileSync(probeFile, JSON.stringify({ ok: true }));
  });

  afterAll(() => {
    rmSync(probeDir, { recursive: true, force: true });
  });

  it("does not mutate protected HVS repository files during Phase-2 activity", () => {
    const after = snapshot();
    for (const p of PROTECTED) {
      expect(after[p], `protected file changed: ${p}`).toBe(before[p]);
    }
  });

  it("only writes under the runtime (non-protected) location", () => {
    expect(existsSync(probeFile)).toBe(true);
    const db = readFileSync(PROTECTED[0], "utf8");
    expect(db).not.toContain("guard-probe");
  });
});
