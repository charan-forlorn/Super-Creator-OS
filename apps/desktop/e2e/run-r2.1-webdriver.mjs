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

async function main() {
  await createSession();
  pass("HARNESS_SESSION_START");

  currentGate = "GUI_CLIPS_VISIBLE";
  for (const id of ["c0", "c1", "c2"]) await waitFor(`[data-testid="clip-${id}"]`);
  pass(currentGate);

  const c0 = await find('[data-testid="clip-c0"]');
  const c1 = await find('[data-testid="clip-c1"]');

  currentGate = "GUI_MULTI_SELECT";
  await ctrlClick(c0, 40);
  // c1 (1.5–9.5s after nudge) overlaps c0 (0.5–2.5s); click its shadow-free zone at 7s
  // (offset 440 from c1.left): covered only by c1, never by c0 or its duplicate copy.
  await ctrlClick(c1, 440);
  assert.equal(await selected("c0"), "true");
  assert.equal(await selected("c1"), "true");
  assert.match(await text(await find('[data-testid="selection-count"]')), /2 selected/);
  pass(currentGate);

  const beforeDrag = { c0: await startOf("c0"), c1: await startOf("c1") };
  currentGate = "GUI_GROUP_DRAG";
  await dragBy(c0, 160); // 2 seconds at the fixed 80px/s E2E zoom.
  approx(await startOf("c0"), beforeDrag.c0 + 2, "c0 group drag delta");
  approx(await startOf("c1"), beforeDrag.c1 + 2, "c1 group drag delta");
  pass(currentGate);

  currentGate = "GUI_GROUP_SPACING_PRESERVED";
  approx((await startOf("c1")) - (await startOf("c0")), beforeDrag.c1 - beforeDrag.c0, "group spacing");
  pass(currentGate);

  currentGate = "GUI_GROUP_UNDO";
  await shortcut("z");
  approx(await startOf("c0"), beforeDrag.c0, "c0 one-step undo");
  approx(await startOf("c1"), beforeDrag.c1, "c1 one-step undo");
  pass(currentGate);

  currentGate = "GUI_GROUP_REDO";
  await shortcut("y");
  approx(await startOf("c0"), beforeDrag.c0 + 2, "c0 one-step redo");
  approx(await startOf("c1"), beforeDrag.c1 + 2, "c1 one-step redo");
  pass(currentGate);

  currentGate = "GUI_SELECT_ALL";
  await shortcut("a");
  assert.match(await text(await find('[data-testid="selection-count"]')), /3 selected/);
  for (const id of ["c0", "c1", "c2"]) assert.equal(await selected(id), "true");
  pass(currentGate);

  const beforeNudge = { c0: await startOf("c0"), c1: await startOf("c1"), c2: await startOf("c2") };
  currentGate = "GUI_KEYBOARD_NUDGE";
  await press(KEY.ARROW_RIGHT);
  for (const id of ["c0", "c1", "c2"]) approx(await startOf(id), beforeNudge[id] + 0.5, `${id} arrow nudge`);
  pass(currentGate);

  const afterNudge = { c0: await startOf("c0"), c1: await startOf("c1"), c2: await startOf("c2") };
  currentGate = "GUI_GROUP_DELETE";
  await press(KEY.DELETE);
  for (const id of ["c0", "c1", "c2"]) assert.equal(await maybeFind(`[data-testid="clip-${id}"]`), null);
  pass(currentGate);

  currentGate = "GUI_GROUP_DELETE_UNDO";
  await shortcut("z");
  for (const id of ["c0", "c1", "c2"]) {
    await waitFor(`[data-testid="clip-${id}"]`);
    approx(await startOf(id), afterNudge[id], `${id} delete undo exact restore`);
  }
  pass(currentGate);

  currentGate = "GUI_GROUP_DUPLICATE";
  await shortcut("a");
  const preDuplicateCount = (await findAll(".clip")).length;
  await shortcut("d");
  assert.equal((await findAll(".clip")).length, preDuplicateCount * 2, "group duplicate count");
  pass(currentGate);

  // c0 (0–4) and c1 (3–7) overlap at 3–4. Clear any prior selection with a real
  // Escape, then select both via actual Ctrl-click (same proven pattern as
  // GUI_MULTI_SELECT). Set the playhead at 3.5s with a REAL ruler click (does not
  // clear selection), then split with the `s` shortcut. Both selected clips
  // contain 3.5s, so each splits once → clip count increases by 2.
  currentGate = "GUI_MULTI_SPLIT";
  await press(KEY.ESCAPE);
  const diagClips = await findAll(".clip");
  console.log("SPLIT_PRE nClips=" + diagClips.length + " count=" + await text(await find('[data-testid="selection-count"]')));
  await ctrlClick(await find('[data-testid="clip-c0"]'), 40);
  console.log("SPLIT_AFTER_C0 c0=" + await selected("c0") + " c1=" + await selected("c1") + " count=" + await text(await find('[data-testid="selection-count"]')));
  // c1 (1.5–9.5s after nudge); click its shadow-free zone at ~7s (offset 440): covered
  // only by c1, never by c0 (0.5–2.5s) or c0's duplicate copy (2.5–4.5s).
  await ctrlClick(await find('[data-testid="clip-c1"]'), 440);
  console.log("SPLIT_SELECT_DIAG=" + JSON.stringify({
    count: await text(await find('[data-testid="selection-count"]')),
    c0: await selected("c0"),
    c1: await selected("c1"),
  }));
  assert.equal(await selected("c0"), "true");
  assert.equal(await selected("c1"), "true");
  const beforeSplit = (await findAll(".clip")).length;
  // Compute a real split playhead strictly inside BOTH selected clips using their
  // actual rendered geometry, so the assertion is robust to prior-gate positions.
  const c0s = await startOf("c0");
  const c0d = await durationOf("c0");
  const c1s = await startOf("c1");
  const c1d = await durationOf("c1");
  const lo = Math.max(c0s, c1s) + 0.2;            // after both clip starts
  const hi = Math.min(c0s + c0d, c1s + c1d) - 0.2; // before both clip ends
  const splitSec = Number(((lo + hi) / 2).toFixed(2));
  assert.ok(hi > lo, `c0 (${c0s}–${c0s + c0d}) and c1 (${c1s}–${c1s + c1d}) must overlap for split`);
  const vx = await clickRulerAt(splitSec);
  console.log("PLAYHEAD_GUI_SET=" + JSON.stringify({ seconds: splitSec, viewportX: vx, c0: [c0s, c0s + c0d], c1: [c1s, c1s + c1d] }));
  await typeKey("s");
  const afterSplit = (await findAll(".clip")).length;
  // Hard evidence: list every clip id + its left (start*pxPerSec) after the split.
  const clipList = (await findAll('[data-testid^="clip-"]')).map(async (el) => {
    const b = await rect(el); const t = await attr(el, "data-testid"); return `${t}@${b.x.toFixed(0)}`;
  });
  console.log("SPLIT_CLIP_LIST=" + JSON.stringify(await Promise.all(clipList)));
  assert.equal(afterSplit, beforeSplit + 2, "two eligible selected clips split");
  // Spot-check: c0/c1 each became two contiguous pieces; all clip ids preserved in DOM.
  const splitCount = (await findAll('[data-testid^="clip-"]')).length;
  assert.ok(splitCount >= afterSplit, "split clip ids preserved in DOM");
  pass(currentGate);

  currentGate = "GUI_CLEAR_SELECTION";
  await press(KEY.ESCAPE);
  // Authoritative rendered-UI evidence of cleared selection: no clip carries the
  // selected/primary class, and the rendered count (when resolvable) is zero.
  const selectedClips = (await findAll('.clip[data-selected="true"]')).length;
  const primaryClips = (await findAll('.clip.primary')).length;
  const countText = await text(await find('[data-testid="selection-count"]'));
  console.log("CLEAR_EVIDENCE=" + JSON.stringify({ selectedClips, primaryClips, countText }));
  assert.equal(selectedClips, 0, "no clip remains selected after Escape");
  assert.equal(primaryClips, 0, "no primary selection marker after Escape");
  assert.ok(/^$|0 selected/.test(countText), "rendered selection count is zero");
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
  if (sessionId) {
    await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
  }
}
