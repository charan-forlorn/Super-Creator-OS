#!/usr/bin/env node
/** Focused probe: reproduce the two-ctrl-click selection on the real app. */
import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const elementRef = (id) => ({ [ELEMENT]: id });
async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, { method, headers: body === undefined ? undefined : { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} ${response.status}`);
  return payload.value;
}
async function find(css) { return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT]; }
async function maybeFind(css) { try { return await find(css); } catch { return null; } }
async function waitFor(css, t = 6000) { const d = Date.now() + t; while (Date.now() < d) { const id = await maybeFind(css); if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id; await sleep(50); } throw new Error("missing " + css); }
async function text(id) { return wd("GET", `/session/${sessionId}/element/${id}/text`); }
async function attr(id, n) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${n}`); }
async function rectOf(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function selCount() { try { return await text(await find('[data-testid="selection-count"]')); } catch { return "<none>"; } }
async function perform(actions) { await wd("POST", `/session/${sessionId}/actions`, { actions }); await wd("DELETE", `/session/${sessionId}/actions`); await sleep(120); }
async function ctrlClick(id, x = 0) {
  await perform([
    { type: "key", id: "k", actions: [{ type: "keyDown", value: "\uE009" }, { type: "pause", duration: 20 }, { type: "pause", duration: 20 }, { type: "keyUp", value: "\uE009" }] },
    { type: "pointer", id: "m", parameters: { pointerType: "mouse" }, actions: [{ type: "pointerMove", duration: 0, origin: elementRef(id), x, y: 0 }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }] },
  ]);
}
async function selected(id) { try { return await attr(await find(`[data-testid="clip-${id}"]`), "data-selected"); } catch { return "<none>"; } }

async function main() {
  const cap = await wd("POST", "/session", { capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [] } } } });
  sessionId = cap.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  await waitFor('[data-testid="clip-c0"]');
  const c0 = await find('[data-testid="clip-c0"]');
  const c1 = await find('[data-testid="clip-c1"]');
  const b0 = await rectOf(c0), b1 = await rectOf(c1);
  console.log("C0_BOX=" + JSON.stringify(b0));
  console.log("C1_BOX=" + JSON.stringify(b1));
  // Escape-clear
  await perform([{ type: "key", id: "k", actions: [{ type: "keyDown", value: "\uE00C" }, { type: "keyUp", value: "\uE00C" }] }]);
  console.log("AFTER_ESC count=" + await selCount() + " c0=" + await selected("c0") + " c1=" + await selected("c1"));
  await ctrlClick(c0, 20);
  console.log("AFTER_C0 count=" + await selCount() + " c0=" + await selected("c0") + " c1=" + await selected("c1"));
  await ctrlClick(c1, 320);
  console.log("AFTER_C1 count=" + await selCount() + " c0=" + await selected("c0") + " c1=" + await selected("c1"));
  // Also try clicking c1 at x=20 (start) and x=160
  await perform([{ type: "key", id: "k", actions: [{ type: "keyDown", value: "\uE00C" }, { type: "keyUp", value: "\uE00C" }] }]);
  await ctrlClick(c0, 20);
  await ctrlClick(c1, 160);
  console.log("TRY_X160 count=" + await selCount() + " c0=" + await selected("c0") + " c1=" + await selected("c1"));
}
try { await main(); }
catch (e) { console.error("PROBE_FAIL", e instanceof Error ? e.stack : e); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
