#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
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
  if (!response.ok) {
    throw new Error(payload?.value?.message ?? `${method} ${path} failed: ${response.status}`);
  }
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
  return (await wd("POST", `/session/${sessionId}/element`, {
    using: "css selector", value: css,
  }))[ELEMENT];
}

async function findAll(css) {
  return (await wd("POST", `/session/${sessionId}/elements`, {
    using: "css selector", value: css,
  })).map((entry) => entry[ELEMENT]);
}

async function maybeFind(css) {
  try { return await find(css); } catch { return null; }
}

async function waitFor(css, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id;
    await sleep(50);
  }
  throw new Error(`${css} not visibly rendered`);
}
async function attr(id, name) {
  return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`);
}

async function prop(id, name) {
  return wd("GET", `/session/${sessionId}/element/${id}/property/${name}`);
}

async function click(id) {
  await wd("POST", `/session/${sessionId}/element/${id}/click`, {});
  await sleep(150);
}

function pass(label) {
  console.log(`${label}=PASS`);
}

async function main() {
  await createSession();
  pass("HARNESS_SESSION_START");

  currentGate = "MULTI_LAYER_VISUAL_STACK";
  await waitFor('[data-preview-layer="v-back"]');
  await waitFor('[data-preview-layer="v-front"]');
  const layers = await findAll("[data-preview-layer]");
  const layerIds = [];
  for (const id of layers) layerIds.push(await attr(id, "data-preview-layer"));
  assert.deepEqual(layerIds, ["v-back", "v-front"]);
  pass(currentGate);
  currentGate = "HIDDEN_LAYER_EXCLUDED";
  assert.equal(await maybeFind('[data-preview-layer="v-hidden"]'), null);
  assert.equal(await maybeFind('[data-preview-visual="p43-hidden"]'), null);
  pass(currentGate);

  currentGate = "CAPTION_Z_LAYER";
  const caption = await waitFor('[data-preview-caption="p43-caption"]');
  assert.equal(await attr(caption, "data-preview-caption"), "p43-caption");
  pass(currentGate);

  currentGate = "DEDICATED_AUDIO_MIX";
  const expectedAudio = ["p43-back", "p43-front", "p43-music"];
  for (const clipId of expectedAudio) {
    assert.ok(await maybeFind(`[data-preview-audio="${clipId}"]`), `missing audio ${clipId}`);
  }
  assert.equal(await maybeFind('[data-preview-audio="p43-hidden"]'), null);
  pass(currentGate);

  currentGate = "VISUAL_VIDEO_MUTED";
  for (const clipId of ["p43-back", "p43-front"]) {
    const video = await waitFor(`[data-preview-visual="${clipId}"]`);
    assert.equal(await prop(video, "muted"), true, `${clipId} visual video must be muted`);
  }
  pass(currentGate);
  currentGate = "MULTI_LAYER_TRANSPORT";
  const seek = await find('[data-testid="transport-seek"]');
  const before = Number(await prop(seek, "value"));
  const play = await find('[data-testid="transport-play-toggle"]');
  await click(play);
  await sleep(650);
  const after = Number(await prop(seek, "value"));
  assert.ok(after > before + 0.1, `playhead must advance: before=${before}, after=${after}`);
  await click(await find('[data-testid="transport-stop"]'));
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
