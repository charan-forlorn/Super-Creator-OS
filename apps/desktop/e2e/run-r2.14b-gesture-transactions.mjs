/**
 * R2.14B real GUI proof: one pointer gesture must produce one history entry.
 * Drives the released Tauri/WebView2 editor through raw W3C WebDriver only.
 */
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const CONTROL = "\uE009";
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
async function createSession() {
  const value = await wd("POST", "/session", {
    capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [] } } },
  });
  sessionId = value.sessionId;
  assert.equal(await wd("GET", `/session/${sessionId}/url`), "http://tauri.localhost/");
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}

async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function attr(id, name) {
  return await wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`);
}
async function rect(id) {
  return await wd("GET", `/session/${sessionId}/element/${id}/rect`);
}
async function maybeFind(css) {
  try { return await find(css); } catch { return null; }
}
async function waitFor(css, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id;
    await sleep(50);
  }
  throw new Error(`${css} was not visibly rendered`);
}
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(100);
}

async function clickAt(id, offsetX = 20) {
  const box = await rect(id);
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(box.x + offsetX), y: Math.round(box.y + box.height / 2) },
    { type: "pointerDown", button: 0 },
    { type: "pointerUp", button: 0 },
  ] }]);
}

async function multiStepDrag(id, deltas) {
  const actions = [
    { type: "pointerMove", duration: 0, origin: elementRef(id), x: 0, y: 0 },
    { type: "pointerDown", button: 0 },
  ];
  for (const x of deltas) {
    actions.push({ type: "pointerMove", duration: 120, origin: "pointer", x, y: 0 });
  }
  actions.push({ type: "pointerUp", button: 0 });
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions }]);
}

async function shortcut(letter) {
  await perform([{ type: "key", id: "keyboard", actions: [
    { type: "keyDown", value: CONTROL }, { type: "keyDown", value: letter },
    { type: "keyUp", value: letter }, { type: "keyUp", value: CONTROL },
  ] }]);
}
async function startOf(id) {
  return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-start"));
}
async function durationOf(id) {
  return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-duration"));
}
function approx(actual, expected, label) {
  assert.ok(Math.abs(actual - expected) < 0.01, `${label}: expected ${expected}, got ${actual}`);
}
function pass(label) { console.log(`${label}=PASS`); }

async function main() {
  await createSession();
  pass("HARNESS_SESSION_START");
  for (const id of ["c0", "c1", "c2"]) await waitFor(`[data-testid="clip-${id}"]`);

  currentGate = "SINGLE_MOVE_MULTI_EVENT_GESTURE";
  const c2 = await find('[data-testid="clip-c2"]');
  await clickAt(c2, 40);
  const moveStart = await startOf("c2");
  await multiStepDrag(c2, [40, 40, 40]);
  approx(await startOf("c2"), moveStart + 1.5, "single move final start");
  pass(currentGate);

  currentGate = "SINGLE_MOVE_ONE_STEP_UNDO";
  await shortcut("z");
  approx(await startOf("c2"), moveStart, "single move one-step undo");
  pass(currentGate);

  currentGate = "NORMAL_RIGHT_TRIM_MULTI_EVENT_GESTURE";
  const c1 = await find('[data-testid="clip-c1"]');
  await clickAt(c1, 200);
  const trimStart = await durationOf("c1");
  const trimRight = await find('[data-testid="clip-c1"] .trim-r');
  await multiStepDrag(trimRight, [-20, -20, -20]);
  approx(await durationOf("c1"), trimStart - 0.75, "normal right trim final duration");
  pass(currentGate);

  currentGate = "NORMAL_RIGHT_TRIM_ONE_STEP_UNDO";
  await shortcut("z");
  approx(await durationOf("c1"), trimStart, "normal right trim one-step undo");
  pass(currentGate);

  currentGate = "NORMAL_LEFT_TRIM_MULTI_EVENT_GESTURE";
  await clickAt(await find('[data-testid="clip-c1"]'), 200);
  const leftTrimStart = await durationOf("c1");
  const trimLeft = await find('[data-testid="clip-c1"] .trim-l');
  await multiStepDrag(trimLeft, [20, 20, 20]);
  approx(await durationOf("c1"), leftTrimStart - 0.75, "normal left trim final duration");
  pass(currentGate);

  currentGate = "NORMAL_LEFT_TRIM_ONE_STEP_UNDO";
  await shortcut("z");
  approx(await durationOf("c1"), leftTrimStart, "normal left trim one-step undo");
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
