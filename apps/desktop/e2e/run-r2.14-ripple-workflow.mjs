#!/usr/bin/env node
/**
 * R2.1 REAL GUI proof runner — raw W3C WebDriver protocol.
 *
 * This is an adapter around tauri-driver 2.0.6's documented `alwaysMatch`
 * requirement. It drives the actual Tauri/WebView2 editor through only
 * standard WebDriver DOM, pointer, and keyboard endpoints. It imports no
 * application store, CommandBus, or project-model APIs.
 */
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const KEY = {
  CONTROL: "\uE009",
  SHIFT: "\uE008",
  DELETE: "\uE017",
  ESCAPE: "\uE00C",
  ARROW_RIGHT: "\uE014",
};

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
  if (!response.ok) {
    const message = payload?.value?.message ?? `${method} ${path} failed: ${response.status}`;
    throw new Error(message);
  }
  return payload.value;
}

async function createSession() {
  const value = await wd("POST", "/session", {
    capabilities: {
      alwaysMatch: {
        browserName: "webview2",
        "tauri:options": { application: APP, args: [] },
      },
    },
  });
  sessionId = value.sessionId;
  assert.equal(await wd("GET", `/session/${sessionId}/url`), "http://tauri.localhost/");
  assert.equal(await wd("GET", `/session/${sessionId}/title`), "HAIOS AI Video Studio — E2E");
  // Deterministic viewport so the styled timeline footer is fully visible.
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}

async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, {
    using: "css selector",
    value: css,
  }))[ELEMENT];
}

async function findAll(css) {
  return (await wd("POST", `/session/${sessionId}/elements`, {
    using: "css selector",
    value: css,
  })).map((entry) => entry[ELEMENT]);
}

async function maybeFind(css) {
  try {
    return await find(css);
  } catch {
    return null;
  }
}

async function waitFor(css, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id;
    await sleep(50);
  }
  throw new Error(`${css} was not visibly rendered by the E2E app`);
}

async function attr(id, name) {
  return await wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`);
}

async function text(id) {
  return await wd("GET", `/session/${sessionId}/element/${id}/text`);
}

async function rect(id) {
  return await wd("GET", `/session/${sessionId}/element/${id}/rect`);
}

async function prop(id, name) {
  return await wd("GET", `/session/${sessionId}/element/${id}/property/${name}`);
}

async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(100);
}

async function ctrlClick(id, offsetX = 0) {
  // W3C pointer `origin: element` offsets from the element CENTER, so we instead
  // compute an absolute viewport coordinate (left + offsetX) for deterministic hits.
  const box = await rect(id);
  const x = Math.round(box.x + offsetX);
  const y = Math.round(box.y + box.height / 2);
  await perform([
    {
      type: "key",
      id: "keyboard",
      actions: [
        { type: "keyDown", value: KEY.CONTROL },
        { type: "pause", duration: 20 },
        { type: "pause", duration: 20 },
        { type: "keyUp", value: KEY.CONTROL },
      ],
    },
    {
      type: "pointer",
      id: "mouse",
      parameters: { pointerType: "mouse" },
      actions: [
        { type: "pointerMove", duration: 0, origin: "viewport", x, y },
        { type: "pointerDown", button: 0 },
        { type: "pointerUp", button: 0 },
        { type: "pause", duration: 0 },
      ],
    },
  ]);
}

async function dragBy(id, x) {
  await perform([
    {
      type: "pointer",
      id: "mouse",
      parameters: { pointerType: "mouse" },
      actions: [
        { type: "pointerMove", duration: 0, origin: elementRef(id), x: 0, y: 0 },
        { type: "pointerDown", button: 0 },
        { type: "pointerMove", duration: 300, origin: "pointer", x, y: 0 },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
}

async function shortcut(letter) {
  await perform([
    {
      type: "key",
      id: "keyboard",
      actions: [
        { type: "keyDown", value: KEY.CONTROL },
        { type: "keyDown", value: letter },
        { type: "keyUp", value: letter },
        { type: "keyUp", value: KEY.CONTROL },
      ],
    },
  ]);
}

async function press(value) {
  await perform([
    {
      type: "key",
      id: "keyboard",
      actions: [
        { type: "keyDown", value },
        { type: "keyUp", value },
      ],
    },
  ]);
}

// Plain (non-modified) character key — used for the split shortcut `s`.
async function typeKey(value) {
  await perform([
    {
      type: "key",
      id: "keyboard",
      actions: [
        { type: "keyDown", value },
        { type: "keyUp", value },
      ],
    },
  ]);
}

// Set the playhead through a real GUI ruler click. The ruler handler sets the
// playhead WITHOUT clearing selection, so a multi-selection survives for split.
async function clickRulerAt(seconds) {
  // The click handler now lives on `.ruler-lane`, whose left edge shares the track's
  // t=0 origin (after the 64px label), so a lane-relative click maps 1:1 to clip time.
  const ruler = await find(".ruler-lane");
  const rulerBox = await rect(ruler);
  const timelineX = Math.round(seconds * 80); // pxPerSec at default zoom 1.
  const viewportX = Math.round(rulerBox.x + timelineX);
  assert.ok(
    viewportX >= rulerBox.x && viewportX <= rulerBox.x + rulerBox.width,
    `playhead ${seconds}s must be inside the ruler lane viewport`,
  );
  await perform([
    {
      type: "pointer",
      id: "mouse",
      parameters: { pointerType: "mouse" },
      actions: [
        { type: "pointerMove", duration: 0, origin: "viewport", x: viewportX, y: Math.round(rulerBox.y + rulerBox.height / 2) },
        { type: "pointerDown", button: 0 },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
  return viewportX;
}

async function clickTrackAt(seconds) {
  let scroll = await find(".timeline-scroll");
  let scrollBox = await rect(scroll);
  const windowBox = await wd("GET", `/session/${sessionId}/window/rect`);
  if (scrollBox.y + 40 > windowBox.height) {
    // Bring the actual timeline viewport into the browser viewport using a
    // genuine wheel gesture before clicking it.
    await perform([
      {
        type: "wheel",
        id: "wheel",
        actions: [{
          type: "scroll",
          x: Math.round(Math.min(windowBox.width - 20, 700)),
          y: Math.round(Math.min(windowBox.height - 20, 500)),
          deltaX: 0,
          deltaY: Math.round(scrollBox.y - windowBox.height / 2),
          duration: 200,
        }],
      },
    ]);
    scroll = await find(".timeline-scroll");
    scrollBox = await rect(scroll);
  }

  const currentScrollLeft = Number(await prop(scroll, "scrollLeft"));
  const desiredLeft = seconds * 80 - scrollBox.width / 2;
  const deltaX = Math.max(0, desiredLeft - currentScrollLeft);
  if (deltaX > 1) {
    // Actual horizontal wheel gesture against the rendered timeline viewport.
    await perform([
      {
        type: "wheel",
        id: "wheel",
        actions: [{
          type: "scroll",
          x: Math.round(scrollBox.x + scrollBox.width / 2),
          y: Math.round(scrollBox.y + scrollBox.height / 2),
          deltaX: Math.round(deltaX),
          deltaY: 0,
          duration: 200,
        }],
      },
    ]);
  }

  const track = await find(".track-video");
  const trackBox = await rect(track);
  const timelineX = Math.round(seconds * 80);
  const viewportX = Math.round(trackBox.x + timelineX);
  assert.ok(
    viewportX >= scrollBox.x && viewportX <= scrollBox.x + scrollBox.width,
    `playhead ${seconds}s must be visible after horizontal scroll`,
  );
  console.log("GUI_SPLIT_TARGET=" + JSON.stringify({
    seconds,
    currentScrollLeft,
    deltaX,
    scrollBox,
    trackBox,
    viewportX,
  }));
  await perform([
    {
      type: "pointer",
      id: "mouse",
      parameters: { pointerType: "mouse" },
      actions: [
        {
          type: "pointerMove",
          duration: 0,
          origin: "viewport",
          x: viewportX,
          y: Math.round(trackBox.y + trackBox.height / 2),
        },
        { type: "pointerDown", button: 0 },
        { type: "pointerUp", button: 0 },
      ],
    },
  ]);
}

async function startOf(id) {
  return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-start"));
}

async function durationOf(id) {
  return Number(await attr(await find(`[data-testid="clip-${id}"]`), "data-duration"));
}

async function selected(id) {
  return attr(await find(`[data-testid="clip-${id}"]`), "data-selected");
}

function approx(actual, expected, label) {
  assert.ok(Math.abs(actual - expected) < 0.01, `${label}: expected ${expected}, got ${actual}`);
}

function pass(label) {
  console.log(`${label}=PASS`);
}


async function clickAt(id, offsetX = 20) {
  const box = await rect(id);
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(box.x + offsetX), y: Math.round(box.y + box.height / 2) },
    { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
  ] }]);
}

async function shiftDelete() {
  await perform([{ type: "key", id: "keyboard", actions: [
    { type: "keyDown", value: KEY.SHIFT }, { type: "keyDown", value: KEY.DELETE },
    { type: "keyUp", value: KEY.DELETE }, { type: "keyUp", value: KEY.SHIFT },
  ] }]);
}

async function main() {
  await createSession();
  pass("HARNESS_SESSION_START");

  currentGate = "RIPPLE_CONTROLS_VISIBLE";
  await waitFor('[data-testid="ripple-delete"]');
  await waitFor('[data-testid="ripple-trim-toggle"]');
  pass(currentGate);

  currentGate = "RIPPLE_DELETE_SHORTCUT";
  await clickAt(await find('[data-testid="clip-c0"]'), 20);
  await press(KEY.DELETE); // remove overlapping c0 so c1 has a hard-cut boundary
  assert.equal(await maybeFind('[data-testid="clip-c0"]'), null);
  await clickAt(await find('[data-testid="clip-c1"]'), 200);
  await shiftDelete();
  assert.equal(await maybeFind('[data-testid="clip-c1"]'), null);
  approx(await startOf("c2"), 2, "ripple-delete downstream shift");
  pass(currentGate);

  currentGate = "RIPPLE_DELETE_ONE_STEP_UNDO";
  await shortcut("z");
  await waitFor('[data-testid="clip-c1"]');
  approx(await startOf("c1"), 1, "c1 ripple-delete undo");
  approx(await startOf("c2"), 10, "c2 ripple-delete undo");
  pass(currentGate);

  currentGate = "RIPPLE_TRIM_REAL_GESTURE";
  await clickAt(await find('[data-testid="clip-c1"]'), 200);
  const toggle = await find('[data-testid="ripple-trim-toggle"]');
  await wd("POST", `/session/${sessionId}/element/${toggle}/click`, {});
  assert.equal(await prop(toggle, "checked"), true);
  const trimRight = await find('[data-testid="clip-c1"] .trim-r');
  await dragBy(trimRight, -80); // 1 second at default 80px/s
  approx(await durationOf("c1"), 7, "c1 ripple-trim duration");
  approx(await startOf("c2"), 9, "c2 ripple-trim downstream shift");
  pass(currentGate);

  currentGate = "RIPPLE_TRIM_ONE_STEP_UNDO";
  await shortcut("z");
  approx(await durationOf("c1"), 8, "c1 ripple-trim undo duration");
  approx(await startOf("c2"), 10, "c2 ripple-trim undo start");
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
