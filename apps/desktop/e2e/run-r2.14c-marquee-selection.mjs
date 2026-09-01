#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const CONTROL = "\uE009";
let sessionId = null;
let currentGate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed`);
  return payload.value;
}
async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function maybeFind(css) { try { return await find(css); } catch { return null; } }
async function waitFor(css, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id;
    await sleep(50);
  }
  throw new Error(`${css} was not visibly rendered`);
}
async function rect(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function selected(id) { return attr(await find(`[data-testid="clip-${id}"]`), "data-selected"); }
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function click(id) {
  const box = await rect(id);
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(box.x + box.width / 2), y: Math.round(box.y + box.height / 2) },
    { type: "pointerDown", button: 0 },
    { type: "pointerUp", button: 0 },
  ] }]);
}
async function marqueeDrag(start, end, additive = false) {
  const pointer = { type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: start.x, y: start.y },
    { type: "pointerDown", button: 0 },
    { type: "pointerMove", duration: 300, origin: "viewport", x: end.x, y: end.y },
    { type: "pointerUp", button: 0 },
  ] };
  if (!additive) return perform([pointer]);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [
    { type: "key", id: "keyboard", actions: [{ type: "keyDown", value: "\uE008" }] },
  ] });
  await sleep(50);
  await perform([pointer]);
}

function pass(label) { console.log(`${label}=PASS`); }

async function main() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  pass("HARNESS_SESSION_START");
  const c0 = await waitFor('[data-testid="clip-c0"]');
  const c1 = await waitFor('[data-testid="clip-c1"]');
  const c2 = await waitFor('[data-testid="clip-c2"]');
  const lane = await find(".track-video .track-lane");
  const b0 = await rect(c0), b1 = await rect(c1), laneBox = await rect(lane);
  const start = {
    x: Math.round(Math.max(laneBox.x + 2, Math.min(b0.x, b1.x) - 12)),
    y: Math.round(laneBox.y + laneBox.height - 2),
  };
  const end = {
    x: Math.round(Math.min(laneBox.x + laneBox.width - 2, Math.max(b0.x + b0.width, b1.x + b1.width) + 12)),
    y: Math.round(laneBox.y + 2),
  };

  currentGate = "MARQUEE_REPLACE_SELECTION";
  await marqueeDrag(start, end);
  assert.equal(await selected("c0"), "true");
  assert.equal(await selected("c1"), "true");
  assert.equal(await selected("c2"), "false");
  pass(currentGate);

  currentGate = "MARQUEE_ADDITIVE_SELECTION";
  await click(c2);
  await marqueeDrag(start, end, true);
  assert.equal(await selected("c0"), "true");
  assert.equal(await selected("c1"), "true");
  assert.equal(await selected("c2"), "true");
  pass(currentGate);
  console.log("REAL_GUI_RUNTIME=PASS");
}

try {
  await main();
} catch (error) {
  console.error(`${currentGate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
