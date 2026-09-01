#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const CTRL = "\uE009";
let sessionId = null;
let gate = "HARNESS_SESSION_START";
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
async function findAll(css) {
  return (await wd("POST", `/session/${sessionId}/elements`, { using: "css selector", value: css })).map((x) => x[ELEMENT]);
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
async function click(id) {
  const b = await rect(id);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{
    type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + b.width / 2), y: Math.round(b.y + b.height / 2) },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
    ],
  }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function clickRulerAt(seconds) {
  const ruler = await find(".ruler-lane");
  const box = await rect(ruler);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{
    type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(box.x + seconds * 80), y: Math.round(box.y + box.height / 2) },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
    ],
  }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}

async function undo() {
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{
    type: "key", id: "keyboard", actions: [
      { type: "keyDown", value: CTRL }, { type: "keyDown", value: "z" },
      { type: "keyUp", value: "z" }, { type: "keyUp", value: CTRL },
    ],
  }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function clipIds() {
  const clips = await findAll(".clip");
  const ids = [];
  for (const id of clips) ids.push(await attr(id, "data-clip-id"));
  return ids.sort();
}
function pass(label) { console.log(`${label}=PASS`); }

async function main() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  pass(gate);
  const media = await waitFor('[data-testid^="media-item-"]');
  await waitFor(".clip");
  const before = await clipIds();

  gate = "MEDIA_BIN_SELECTION";
  await click(media);
  assert.equal(await attr(media, "data-selected"), "true");
  pass(gate);

  gate = "INSERT_OVERWRITE_CONTROLS_VISIBLE";
  const insert = await waitFor('[data-testid="insert-edit"]');
  const overwrite = await waitFor('[data-testid="overwrite-edit"]');
  pass(gate);
  await clickRulerAt(10);

  gate = "INSERT_AT_PLAYHEAD_ONE_UNDO";
  await click(insert);
  const afterInsert = await clipIds();
  assert.notDeepEqual(afterInsert, before);
  await undo();
  assert.deepEqual(await clipIds(), before);
  pass(gate);

  gate = "OVERWRITE_AT_PLAYHEAD_ONE_UNDO";
  await click(overwrite);
  assert.notDeepEqual(await clipIds(), before);
  await undo();
  assert.deepEqual(await clipIds(), before);
  pass(gate);
  console.log("REAL_GUI_RUNTIME=PASS");
}
try {
  await main();
} catch (error) {
  console.error(`${gate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
