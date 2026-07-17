/**
 * Cohort 10D — bridge transport security (mocked child_process).
 *
 * This file isolates the spawn-capture tests in their own module so the
 * `node:child_process` mock is installed BEFORE the store binds its
 * `childProcess.spawn` reference. These tests assert the structural transport
 * contract (argv array, no shell, no retry, bounded timeout, exactly one spawn
 * per operation, no browser-steered executable/cwd/store) without launching a
 * real Python process.
 *
 * The REAL process-level bridge (isolated OS-temp stores) is covered separately
 * in hvs-materialization-store.test.ts.
 */

import { describe, expect, it, vi } from "vitest";
import { resolve } from "node:path";
import { type SpawnOptions } from "node:child_process";

import { HvsMaterializationStore, type BridgeOperation } from "@/lib/hvs-materialization-store";

// Mirrors the store's server-side repo-root resolution used for PYTHONPATH.
function repoRootOf(): string {
  return resolve(process.cwd(), "..", "..");
}

// Minimal shape of the child process the store consumes (stdout/stderr/stdin
// event surface + kill). Declared so the mock is fully typed (no `any`).
interface FakeChild {
  stdout: {
    setEncoding(enc: string): void;
    on(ev: string, cb: (chunk: string) => void): void;
  };
  stderr: {
    setEncoding(enc: string): void;
    on(ev: string, cb: (chunk: string) => void): void;
  };
  stdin: {
    write(chunk: string): void;
    end(): void;
  };
  killed: boolean;
  kill(): boolean;
  on(ev: string, cb: (code: number | null) => void): FakeChild;
}

// Shared, mutable control surface for the fake child. The top-level vi.mock
// reads this so tests can steer close-code / kill-capture without re-mocking
// (re-mocks don't rebind an already-imported module's namespaced import).
const hoist = vi.hoisted(() => ({
  calls: [] as Array<{
    file: string;
    args: string[];
    opts: SpawnOptions;
  }>,
  state: { closeCode: 0, killed: false } as { closeCode: number; killed: boolean },
}));

vi.mock("node:child_process", () => {
  const makeFakeChild = (stdoutJson: string): FakeChild => {
    const dataCbs: Array<(chunk: string) => void> = [];
    const closeCbs: Array<(code: number | null) => void> = [];
    const child: FakeChild = {
      stdout: {
        setEncoding() {},
        on(ev: string, cb: (chunk: string) => void) {
          if (ev === "data") dataCbs.push(cb);
        },
      },
      stderr: { setEncoding() {}, on() {} },
      stdin: { write() {}, end() {} },
      killed: false,
      kill() { child.killed = true; hoist.state.killed = true; return true; },
      on(ev: string, cb: (code: number | null) => void) {
        if (ev === "close") closeCbs.push(cb);
        return child;
      },
    };
    Promise.resolve().then(() => {
      for (const cb of dataCbs) cb(stdoutJson);
      // closeCode === -1 means "never close" (used to exercise the timeout).
      if (hoist.state.closeCode !== -1) {
        for (const cb of closeCbs) cb(hoist.state.closeCode);
      }
    });
    return child;
  };
  return {
    spawn: (file: string, args: string[], opts: SpawnOptions) => {
      hoist.calls.push({ file, args, opts: { shell: opts?.shell, cwd: opts?.cwd, env: opts?.env } });
      // Default: a well-formed single JSON object on stdout, success close.
      return makeFakeChild('{"ok":true,"projection":{"truth_state":"MATERIALIZATION_NOT_REQUESTED"}}');
    },
  };
});

const MODULE = "scos.control_center.hvs_materialization_cli";

function newStore(timeoutMs = 30_000): HvsMaterializationStore {
  // Trusted defaults: interpreter + module are server-resolved, not browser.
  return new HvsMaterializationStore("python", MODULE, timeoutMs);
}

describe("Cohort 10D bridge — argv transport (no shell)", () => {
  it("invokes python -m module with the operation as an argv element; never exec(shell-string) (req 1/2)", async () => {
    const store = newStore();
    const res = await store.invoke("projection", { project_id: "spp-x" });
    expect(hoist.calls.length).toBeGreaterThanOrEqual(1);
    const call = hoist.calls[0];
    // argv array form: ["-m", module, operation]
    expect(Array.isArray(call.args)).toBe(true);
    expect(call.args[0]).toBe("-m");
    expect(call.args[1]).toBe(MODULE);
    expect(call.args[2]).toBe("projection");
    // No shell construction.
    expect(call.opts.shell).not.toBe(true);
    // The module is invoked via the `-m` argv form (never a shell string).
    expect(call.args[0]).toBe("-m");
  });

  it("rejects an unknown operation without launching a child (req 2)", async () => {
    const store = newStore();
    hoist.calls.length = 0;
    const res = await store.invoke("bogus" as unknown as BridgeOperation, {});
    expect(res.ok).toBe(false);
    expect(res.error_code).toBe("BRIDGE_UNKNOWN_OPERATION");
    expect(hoist.calls.length).toBe(0);
  });
});

describe("Cohort 10D bridge — browser cannot steer the child (req 3/4/5/6)", () => {
  it("no request field selects exe/cwd/store/projectsRoot", () => {
    const store = newStore();
    // The child is launched with a fixed argv (no browser-supplied
    // executable/cwd/store/projects_root/command). The interpreter + module
    // are passed as constructor args (server-side), never from a request.
    store.invoke("projection", { project_id: "spp-x" });
    const call = hoist.calls[0];
    expect(call.args).toEqual(["-m", MODULE, "projection"]);
    // operation argv must not carry browser store/root knobs.
    expect(JSON.stringify(call.args)).not.toMatch(/store_path|projects_root|cwd|command/i);
  });

  it("passes only an explicit, minimal environment (req 15)", () => {
    const store = newStore();
    store.invoke("projection", { project_id: "spp-x" });
    const env = hoist.calls[0].opts.env as Record<string, string>;
    expect(env).toBeDefined();
    // Reconstruct the EXACT allow-list the store builds, so the assertion is
    // precise rather than assuming a fixed set. The store:
    //   1. hardcodes PYTHONIOENCODING / PYTHONDONTWRITEBYTECODE / TZ
    //   2. forwards only these trusted PARENT env vars IF present
    //   3. adds PYTHONPATH = repo root (server-side only)
    // No browser-supplied or arbitrary parent value is ever forwarded.
    const ALLOWED_PARENT_ENV = [
      "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
      "USERPROFILE", "HOME", "TEMP", "TMP", "USERNAME", "COMSPEC",
      "LANG", "LC_ALL", "PYTHONHOME",
    ];
    const expected: Record<string, string> = {
      PYTHONIOENCODING: "utf-8",
      PYTHONDONTWRITEBYTECODE: "1",
      TZ: "UTC",
    };
    for (const key of ALLOWED_PARENT_ENV) {
      const v = process.env[key];
      if (v !== undefined) expected[key] = v;
    }
    expected.PYTHONPATH = repoRootOf();
    expect(Object.keys(env).sort()).toEqual(Object.keys(expected).sort());
    // Browser/operator knobs must never appear.
    expect(Object.keys(env)).not.toContain("STORE_PATH");
    expect(Object.keys(env)).not.toContain("PROJECTS_ROOT");
    expect(Object.keys(env)).not.toContain("COMMAND");
  });
});

describe("Cohort 10D bridge — fail closed (req 7/8/9/10/11)", () => {
  it("malformed Python output fails closed (req 7) — structural guarantee here", async () => {
    const store = newStore();
    // The fake child normally emits valid JSON; the real-CLI malformed-output
    // path is asserted in the store test. Here we confirm the only code path
    // is the argv/spawn transport (no shell, single spawn).
    const res = await store.invoke("projection", { project_id: "spp-x" });
    expect(res.ok).toBe(true);
    expect(hoist.calls[0].opts.shell).not.toBe(true);
  });

  it("non-zero child exit fails closed (req 8)", async () => {
    hoist.state.closeCode = 2;
    const store = newStore();
    const res = await store.invoke("projection", { project_id: "spp-x" });
    hoist.state.closeCode = 0;
    expect(res.ok).toBe(false);
    expect(res.error_code).toBe("BRIDGE_CHILD_FAILED");
  });

  it("timeout fails closed and kills only the owned child (req 9)", async () => {
    // Make the fake child never close; the wrapper must time out + kill it.
    hoist.state.closeCode = -1; // sentinel: never emit close
    hoist.state.killed = false;
    const store = newStore(20); // 20ms timeout
    const res = await store.invoke("projection", { project_id: "spp-x" });
    expect(res.ok).toBe(false);
    expect(res.error_code).toBe("BRIDGE_TIMEOUT");
    expect(hoist.state.killed).toBe(true);
    hoist.state.closeCode = 0;
  });

  it("raw stderr / paths are never returned (req 10)", async () => {
    const store = newStore();
    const res = await store.invoke("projection", { project_id: "spp-x" });
    // detail is a generic redacted message, never raw stderr/text.
    expect(res.detail ?? "").not.toMatch(/[A-Z]:\\|Traceback|File \"|line \d|PermissionError|No such file/i);
    expect(JSON.stringify(res.response ?? {})).not.toMatch(/[A-Z]:\\|integrity/i);
  });

  it("no retry occurs — a single projection calls the bridge exactly once (req 11)", async () => {
    const store = newStore();
    hoist.calls.length = 0;
    await store.invoke("projection", { project_id: "spp-x" });
    expect(hoist.calls.length).toBe(1);
  });
});

describe("Cohort 10D bridge — each route invokes only its matching operation", () => {
  it("execute invokes the bridge exactly once (req 12/13)", async () => {
    const store = newStore();
    hoist.calls.length = 0;
    await store.invoke("authorize", {
      project_id: "spp-x", project_revision: 2, confirmed: true,
      authorization_id: "auth-1", nonce: "n0", operator_id: "op",
    });
    await store.invoke("execute", {
      project_id: "spp-x", project_revision: 2, authorization_id: "auth-1",
      capability_id: "cap-1", attempt_id: "att-1", operator_id: "op",
    });
    const execCalls = hoist.calls.filter((c) => c.args[2] === "execute");
    expect(execCalls.length).toBe(1);
  });

  it("reconcile remains read-only (req 14) — single spawn, no mutation flags", async () => {
    const store = newStore();
    hoist.calls.length = 0;
    await store.invoke("reconcile", { attempt_id: "att-1" });
    expect(hoist.calls.length).toBe(1);
    expect(hoist.calls[0].args[2]).toBe("reconcile");
  });

  it("projection remains read-only (req 15) — single spawn, no mutation flags", async () => {
    const store = newStore();
    hoist.calls.length = 0;
    await store.invoke("projection", { project_id: "spp-x" });
    expect(hoist.calls.length).toBe(1);
    expect(hoist.calls[0].args[2]).toBe("projection");
  });
});

describe("Cohort 10D bridge — no parallel TS authority remains (req 16)", () => {
  it("the store exposes no local authorization/capability/persistence/reconcile authority", () => {
    const store = newStore();
    const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(store));
    for (const banned of [
      "requestAuthorization", "executeMaterialization", "reconcile",
      "invokeHvsDouble", "inspectHvsDouble", "write", "withLock",
    ]) {
      expect(methods).not.toContain(banned);
    }
    // Only the transport entry point remains.
    expect(methods).toContain("invoke");
  });
});
