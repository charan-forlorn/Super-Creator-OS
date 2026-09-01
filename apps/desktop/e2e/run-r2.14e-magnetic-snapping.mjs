#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const ALT = "\uE00A";
let sessionId = null;
let currentGate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const elementRef = (id) => ({ [ELEMENT]: id });

async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed: ${response.status}`);
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
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function rect(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function exec(script, args = []) {
  return wd("POST", `/session/${sessionId}/execute/sync`, { script, args });
}
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function click(id) {
  await wd("POST", `/session/${sessionId}/element/${id}/click`, {});
  await sleep(100);
}
function approx(actual, expected, label, tolerance = 0.02) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: expected ${expected}, got ${actual}`);
}
function pass(label) { console.log(`${label}=PASS`); }
async function drag(id, dx, alt = false) {
  const pointer = {
    type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin: elementRef(id), x: 0, y: 0 },
      { type: "pointerDown", button: 0 },
      { type: "pointerMove", duration: 100, origin: "pointer", x: Math.trunc(dx / 3), y: 0 },
      { type: "pointerMove", duration: 100, origin: "pointer", x: Math.trunc(dx / 3), y: 0 },
      { type: "pointerMove", duration: 100, origin: "pointer", x: dx - 2 * Math.trunc(dx / 3), y: 0 },
      { type: "pause", duration: 100 },
      { type: "pointerUp", button: 0 },
    ],
  };
  if (!alt) return perform([pointer]);
  const keyboard = { type: "key", id: "keyboard", actions: [
    { type: "keyDown", value: ALT },
    { type: "pause", duration: 0 },
    { type: "pause", duration: 100 },
    { type: "pause", duration: 100 },
    { type: "pause", duration: 100 },
    { type: "pause", duration: 100 },
    { type: "keyUp", value: ALT },
  ] };
  await perform([pointer, keyboard]);
}
async function startOf(id) { return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-start")); }
async function durationOf(id) { return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-duration")); }
async function undo() {
  await perform([{ type: "key", id: "keyboard", actions: [
    { type: "keyDown", value: "\uE009" }, { type: "keyDown", value: "z" },
    { type: "keyUp", value: "z" }, { type: "keyUp", value: "\uE009" },
  ] }]);
}
async function clickViewport(x, y) {
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(x), y: Math.round(y) },
    { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
  ] }]);
}

async function main() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  pass("HARNESS_SESSION_START");

  currentGate = "SNAP_CONTROL_VISIBLE";
  const snapToggle = await waitFor('[data-testid="snap-toggle"]');
  const c2 = await waitFor('[data-testid="clip-c2"]');
  pass(currentGate);
  await click(snapToggle);

  await exec(`window.__r214eGuides=[]; new MutationObserver(() => {
    document.querySelectorAll('[data-testid="snap-guide"]').forEach((el) => {
      window.__r214eGuides.push({ target: el.getAttribute('data-snap-target'), sec: el.getAttribute('data-guide-sec') });
    });
  }).observe(document.body,{subtree:true,childList:true,attributes:true}); return true;`);
  currentGate = "MOVE_START_EDGE_SNAP";
  await drag(c2, -72);
  approx(await startOf("c2"), 9, "start-edge snap");
  pass(currentGate);

  currentGate = "SNAP_GUIDE_RUNTIME";
  const guides = await exec("return window.__r214eGuides || [];");
  assert.ok(guides.some((g) => g.target === "clip-end" && Number(g.sec) === 9), JSON.stringify(guides));
  pass(currentGate);

  currentGate = "ONE_GESTURE_ONE_UNDO";
  await undo();
  approx(await startOf("c2"), 10, "snapped move undo");
  pass(currentGate);

  currentGate = "ALT_BYPASS";
  await drag(await find('[data-testid="clip-c2"]'), -72, true);
  approx(await startOf("c2"), 9.1, "alt bypass raw move");
  await undo();
  pass(currentGate);

  currentGate = "SNAP_DISABLED_BYPASS";
  await click(snapToggle);
  await drag(await find('[data-testid="clip-c2"]'), -72);
  approx(await startOf("c2"), 9.1, "disabled snap raw move");
  await undo();
  await click(snapToggle);
  pass(currentGate);
  currentGate = "TRIM_EDGE_SNAP";
  const trimRight = await find('[data-testid="clip-c2"] .trim-r');
  await drag(trimRight, -72);
  approx(await durationOf("c2"), 1, "right trim snapped to grid 11s");
  await undo();
  approx(await durationOf("c2"), 2, "right trim undo");
  pass(currentGate);

  currentGate = "MOVE_END_EDGE_SNAP";
  const ruler = await find('.ruler-lane');
  const rulerBox = await rect(ruler);
  await clickViewport(rulerBox.x + 12.85 * 80, rulerBox.y + rulerBox.height / 2);
  await drag(await find('[data-testid="clip-c2"]'), 64);
  approx(await startOf("c2"), 10.85, "end-edge snap to playhead");
  await undo();
  approx(await startOf("c2"), 10, "end-edge snap undo");
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
