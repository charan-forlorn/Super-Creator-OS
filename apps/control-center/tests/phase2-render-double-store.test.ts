import { describe, expect, it, vi } from "vitest";

/**
 * Phase 2 — render-double at the bridge layer (no UI, no real Python).
 *
 * Mirrors tests/hvs-materialization-bridge-mock.test.ts: a hoisted fake child
 * process emits a deterministic RENDER_SUCCEEDED package on stdout for the
 * "execute" operation. Asserts: single spawn, shell:false, argv shape, one HVS
 * call, and that a non-zero exit maps to a bridge failure classification.
 */

const MODULE = "scos.control_center.hvs_render_cli";

const { state, spawn } = vi.hoisted(() => {
  const state = { stdout: "", closeCode: 0 };
  const spawn = vi.fn((_cmd: string, _args: string[], _opts: unknown) => {
    const listeners: Record<string, Array<(arg?: unknown) => void>> = {};
    const emit = (event: string, arg?: unknown) => {
      (listeners[event] ?? []).forEach((cb) => cb(arg));
    };
    const on = (event: string, cb: (arg?: unknown) => void) => {
      (listeners[event] ??= []).push(cb);
      if (event === "close") queueMicrotask(() => emit("close", state.closeCode));
    };
    // Emit the deterministic package on stdout, then close.
    queueMicrotask(() => {
      emit("data", state.stdout);
      emit("close", state.closeCode);
    });
    const stream = { on, setEncoding: () => undefined, write: () => undefined };
    return {
      stdout: stream,
      stderr: stream,
      on,
      kill: () => undefined,
      pid: 1,
      killed: false,
      connected: true,
    } as unknown as import("node:child_process").ChildProcess;
  });
  return { state, spawn };
});

vi.mock("node:child_process", async () => {
  const actual = await vi.importActual<typeof import("node:child_process")>("node:child_process");
  return { ...actual, spawn };
});

describe("Phase 2 render-double store seam", () => {
  it("spawns the python CLI without a shell and parses a succeeded package", async () => {
    state.stdout = JSON.stringify({
      ok: true,
      state: "RENDER_SUCCEEDED",
      attempt_id: "att-1",
      render_calls: 1,
      outcome: "success",
      artifact: { filename: "out.mp4", sha256: "deadbeef" },
    });
    state.closeCode = 0;

    const { HvsRenderStore } = await import("@/lib/hvs-render-store");
    const store = new HvsRenderStore();
    const result = await store.invoke("execute", { projectId: "spp-abcdef123456" });

    expect(spawn).toHaveBeenCalledTimes(1);
    const [, args, opts] = spawn.mock.calls[0];
    expect((opts as { shell?: boolean }).shell ?? false).toBe(false);
    expect(args).toContain("-m");
    expect(args).toContain(MODULE);
    expect(args).toContain("execute");
    expect(result.ok).toBe(true);
    expect(result.response).toMatchObject({ ok: true, state: "RENDER_SUCCEEDED" });
  });

  it("maps a non-zero child exit to a bridge failure classification", async () => {
    state.closeCode = 2;
    const { HvsRenderStore } = await import("@/lib/hvs-render-store");
    const store = new HvsRenderStore();
    const result = await store.invoke("execute", {});
    expect(result.ok).toBe(false);
    expect(result.error_code).toBe("BRIDGE_CHILD_FAILED");
  });
});
