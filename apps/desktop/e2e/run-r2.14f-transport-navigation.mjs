#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const SHIFT = "\uE008";
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
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function key(value, shift = false) {
  const actions = [];
  if (shift) actions.push({ type: "keyDown", value: SHIFT });
  actions.push({ type: "keyDown", value }, { type: "keyUp", value });
  if (shift) actions.push({ type: "keyUp", value: SHIFT });
  await perform([{ type: "key", id: "keyboard", actions }]);
}
async function click(id) {
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: { [ELEMENT]: id }, x: 0, y: 0 },
    { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
  ] }]);
}
async function playhead() {
  return Number(await attr(await find('[data-testid="transport-seek"]'), "value"));
}
async function clipStart(id) {
  return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-start"));
}
function approx(actual, expected, label, tolerance = 0.03) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: expected ${expected}, got ${actual}`);
}
function pass(label) { console.log(`${label}=PASS`); }

async function main() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  pass("HARNESS_SESSION_START");

  currentGate = "TRANSPORT_CONTROLS_VISIBLE";
  const playToggle = await waitFor('[data-testid="transport-play-toggle"]');
  await waitFor('[data-testid="transport-seek"]');
  const zoomFit = await waitFor('[data-testid="zoom-fit"]');
  pass(currentGate);

  currentGate = "HOME_END_NAVIGATION";
  await key("\uE011");
  approx(await playhead(), 0, "home playhead");
  await key("\uE010");
  const end = await playhead();
  assert.ok(end > 0, `end playhead expected > 0, got ${end}`);
  pass(currentGate);
  currentGate = "FRAME_AND_COARSE_NAVIGATION";
  await key("\uE00C");
  await key("\uE010");
  const atEnd = await playhead();
  await key("\uE012");
  const frameBack = await playhead();
  assert.ok(atEnd - frameBack > 0 && atEnd - frameBack < 0.1, `frame step=${atEnd - frameBack}`);
  await key("\uE012", true);
  approx(await playhead(), frameBack - 1, "coarse step", 0.04);
  pass(currentGate);

  currentGate = "SELECTION_ARROW_REMAINS_CLIP_NUDGE";
  const c2 = await waitFor('[data-testid="clip-c2"]');
  await click(c2);
  const playheadBeforeNudge = await playhead();
  const clipBefore = await clipStart("c2");
  await key("\uE012");
  approx(await clipStart("c2"), clipBefore - 0.5, "selected clip nudge");
  approx(await playhead(), playheadBeforeNudge, "playhead unchanged during clip nudge");
  pass(currentGate);

  currentGate = "SPACE_TRANSPORT_TOGGLE";
  await key("\uE00C");
  await key("\uE011");
  await key("\uE00D");
  assert.equal(await attr(playToggle, "data-transport-rate"), "1");
  await key("\uE00D");
  assert.equal(await attr(playToggle, "data-transport-rate"), "0");
  pass(currentGate);
  currentGate = "JKL_TRANSPORT_FOUNDATION";
  await key("\uE014", true);
  approx(await playhead(), 1, "coarse forward to reverse start", 0.04);
  await key("j");
  assert.equal(await attr(playToggle, "data-transport-rate"), "-1");
  const reverseStart = await playhead();
  await sleep(350);
  assert.ok(await playhead() < reverseStart - 0.15, `reverse playhead did not move: ${reverseStart} -> ${await playhead()}`);
  await key("k");
  assert.equal(await attr(playToggle, "data-transport-rate"), "0");
  await key("l");
  assert.equal(await attr(playToggle, "data-transport-rate"), "1");
  await key("k");
  pass(currentGate);

  currentGate = "GAP_TRANSPORT_CONTINUITY";
  await key("\uE00C");
  await key("\uE011");
  for (let i = 0; i < 9; i += 1) await key("\uE014", true);
  approx(await playhead(), 9, "gap start", 0.04);
  await key("l");
  const gapStart = await playhead();
  await sleep(450);
  await key("k");
  assert.ok(await playhead() > gapStart + 0.2, `gap transport stalled: ${gapStart} -> ${await playhead()}`);
  pass(currentGate);

  currentGate = "ZOOM_TO_FIT";
  const zoomRange = await waitFor('[data-testid="timeline-zoom-range"]');
  const zoomIn = await waitFor('[data-testid="zoom-in"]');
  await click(zoomIn);
  await click(zoomIn);
  const zoomBeforeFit = Number(await attr(zoomRange, "value"));
  await click(zoomFit);
  const zoomAfterFit = Number(await attr(zoomRange, "value"));
  assert.ok(zoomAfterFit < zoomBeforeFit, `zoom fit did not reduce zoom: ${zoomBeforeFit} -> ${zoomAfterFit}`);
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
