#!/usr/bin/env node
/** R2.1 PHASE 1 probe2: computed position of timeline vs a normal-flow clip. */
import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, { method, headers: body === undefined ? undefined : { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} ${response.status}`);
  return payload.value;
}
async function find(css) { return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT]; }
async function maybeFind(css) { try { return await find(css); } catch { return null; } }
async function waitFor(css, t = 6000) { const d = Date.now() + t; while (Date.now() < d) { const id = await maybeFind(css); if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id; await sleep(50); } throw new Error("missing " + css); }
async function rectOf(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function propOf(id, name) { try { return await wd("GET", `/session/${sessionId}/element/${id}/property/${name}`); } catch { return null; } }
async function perform(actions) { await wd("POST", `/session/${sessionId}/actions`, { actions }); await wd("DELETE", `/session/${sessionId}/actions`); await sleep(150); }

async function main() {
  const cap = await wd("POST", "/session", { capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [] } } } });
  sessionId = cap.sessionId;
  await waitFor('[data-testid="clip-c0"]');
  const win = await wd("GET", `/session/${sessionId}/window/rect`);
  const html = await find("html");
  const timeline = await find(".timeline");
  const scroll = await find(".timeline-scroll");
  const c0 = await find('[data-testid="clip-c0"]');
  const report = async (tag) => {
    const t = await rectOf(timeline), s = await rectOf(scroll), c = await rectOf(c0);
    const st = await propOf(html, "scrollTop");
    console.log(`${tag}|html.scrollTop=${st}|timeline.y=${t.y.toFixed(1)}.pos=${await propOf(timeline,"position")}|scroll.y=${s.y.toFixed(1)}.pos=${await propOf(scroll,"position")}|c0.y=${c.y.toFixed(1)}.pos=${await propOf(c0,"position")}|viewportH=${win.height}`);
  };
  await report("INITIAL");
  // Force document scroll via repeated center wheels.
  for (let i = 0; i < 8; i++) {
    await perform([{ type: "wheel", id: "w", actions: [{ type: "scroll", x: Math.round(win.width / 2), y: Math.round(win.height / 2), deltaX: 0, deltaY: 250, duration: 40 }] }]);
  }
  await report("AFTER_WHEEL_MAX");
}
try { await main(); }
catch (e) { console.error("PROBE2_FAIL", e instanceof Error ? e.stack : e); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
