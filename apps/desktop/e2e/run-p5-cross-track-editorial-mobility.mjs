#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";

const DRIVER = process.env.HAIOS_WEBDRIVER_URL ?? "http://127.0.0.1:4444";
const APP = process.env.HAIOS_APP_PATH;
assert.ok(APP, "HAIOS_APP_PATH is required for Phase 5 qualification");
assert.ok(fs.existsSync(APP), `HAIOS_APP_PATH does not exist: ${APP}`);
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const CONTROL = "\uE009";
let sessionId = null;
let gate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const pass = (name) => console.log(`${name}=PASS`);

async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed ${response.status}`);
  return payload.value;
}

async function createSession() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2",
    "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  await waitFor('[data-testid="track-add-video"]');
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
async function click(id) { await wd("POST", `/session/${sessionId}/element/${id}/click`, {}); await sleep(120); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function exec(script, args = []) { return wd("POST", `/session/${sessionId}/execute/sync`, { script, args }); }
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(150);
}
async function shortcut(letter) {
  await perform([{ type: "key", id: "keyboard", actions: [
    { type: "keyDown", value: CONTROL }, { type: "keyDown", value: letter },
    { type: "keyUp", value: letter }, { type: "keyUp", value: CONTROL },
  ] }]);
}
async function ctrlClickClip(clipId) {
  const id = await find(`[data-testid="clip-${clipId}"]`);
  const origin = { [ELEMENT]: id };
  await perform([
    { type: "key", id: "keyboard", actions: [
      { type: "keyDown", value: CONTROL }, { type: "pause", duration: 40 },
      { type: "pause", duration: 40 }, { type: "keyUp", value: CONTROL },
    ] },
    { type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin, x: 0, y: 0 },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
      { type: "pause", duration: 40 },
    ] },
  ]);
}
async function dragClipToTrack(clipId, targetTrackId, dx = 0) {
  const clip = await find(`[data-testid="clip-${clipId}"]`);
  const lane = await find(`[data-track-id="${targetTrackId}"] .track-lane`);
  const offsetX = await exec(`const c=document.querySelector(arguments[0]).getBoundingClientRect(); const l=document.querySelector(arguments[1]).getBoundingClientRect(); return c.left+c.width/2+arguments[2]-(l.left+l.width/2);`, [`[data-testid="clip-${clipId}"]`, `[data-track-id="${targetTrackId}"] .track-lane`, dx]);
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: { [ELEMENT]: clip }, x: 0, y: 0 },
    { type: "pointerDown", button: 0 },
    { type: "pointerMove", duration: 180, origin: { [ELEMENT]: lane }, x: Math.round(offsetX), y: 0 },
    { type: "pointerUp", button: 0 },
  ] }]);
}
async function clipTrack(clipId) {
  return exec(`return document.querySelector(arguments[0])?.closest('[data-track-id]')?.getAttribute('data-track-id') ?? null;`, [`[data-testid="clip-${clipId}"]`]);
}
async function selectedIds() {
  return exec(`return Array.from(document.querySelectorAll('.clip[data-selected="true"]')).map((el) => el.getAttribute('data-clip-id')).sort();`);
}
async function startOf(clipId) { return Number(await attr(await find(`[data-testid="clip-${clipId}"]`), "data-start")); }
async function playhead() { return Number(await attr(await find('[data-testid="transport-seek"]'), "value")); }
async function errorText() { return exec(`return document.querySelector('.error-toast')?.textContent ?? '';`); }
async function selectedTrackId() { return exec(`return document.querySelector('.track.target-selected')?.getAttribute('data-track-id') ?? null;`); }

function fixture(id = "p5-pointer", transitions = false) {
  const clip = (clipId, trackId, start, transitionIn = null) => ({
    id: clipId, assetId: "asset", trackId, start, inPoint: 0, duration: 2, playbackRate: 1,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn,
    audio: { gainDb: 0, muted: false },
  });
  const track = (trackId, kind, clips = [], locked = false) => ({
    id: trackId, kind, clips, captions: [], visible: true, muted: false, locked,
  });
  const sourceVideo = transitions
    ? [clip("lead", "v1", 0), clip("fade", "v1", 1, { type: "crossfade", duration: 1 })]
    : [clip("v1-clip", "v1", 1)];
  return {
    schemaVersion: 2, id, name: "Phase 5 GUI Qualification",
    createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
    assets: [{ id: "asset", name: "sample.mp4", sourcePath: "E2E_FIXTURE_SAMPLE_MP4", kind: "video", durationSec: 12, width: 320, height: 240, fps: 25, hasAudio: true, createdAt: new Date(0).toISOString() }],
    tracks: [
      track("v1", "video", sourceVideo),
      track("v2", "video", transitions ? [] : [clip("v2-clip", "v2", 4)]),
      track("v3", "video"), track("v-locked", "video", [], true),
      track("a1", "audio", [clip("a1-clip", "a1", 1)]), track("a2", "audio"),
    ], durationSec: 8, aspectRatio: "1920x1080",
  };
}
async function load(project) {
  const loaded = await exec(`window.dispatchEvent(new CustomEvent("haios-e2e-load-project", { detail: arguments[0] })); return document.documentElement.getAttribute("data-e2e-project-loaded");`, [project]);
  assert.equal(loaded, project.id);
  const firstClipId = project.tracks.flatMap((track) => track.clips).at(0)?.id;
  if (firstClipId) await waitFor(`[data-testid="clip-${firstClipId}"]`);
  await sleep(100);
}

async function main() {
  await createSession();
  await load(fixture("p5-single"));
  pass(gate);

  gate = "SINGLE_VIDEO_CROSS_TRACK_MOVE";
  const playheadBefore = await playhead();
  await click(await find('[data-testid="clip-v1-clip"]'));
  assert.deepEqual(await selectedIds(), ["v1-clip"]);
  await dragClipToTrack("v1-clip", "v2");
  assert.equal(await clipTrack("v1-clip"), "v2");
  assert.equal(await attr(await find('[data-testid="clip-v1-clip"]'), "data-primary"), "true");
  assert.equal(await playhead(), playheadBefore);
  pass(gate);

  gate = "CROSS_TRACK_UNDO_EXACT";
  await shortcut("z");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.deepEqual(await selectedIds(), ["v1-clip"]);
  assert.equal(await playhead(), playheadBefore);
  pass(gate);

  gate = "CROSS_TRACK_REDO_EXACT";
  await shortcut("y");
  assert.equal(await clipTrack("v1-clip"), "v2");
  assert.deepEqual(await selectedIds(), ["v1-clip"]);
  assert.equal(await playhead(), playheadBefore);
  pass(gate);

  gate = "SINGLE_AUDIO_CROSS_TRACK_MOVE";
  await load(fixture("p5-audio"));
  await dragClipToTrack("a1-clip", "a2");
  assert.equal(await clipTrack("a1-clip"), "a2");
  pass(gate);

  gate = "MULTI_SELECTION_CROSS_TRACK_ATOMIC";
  await load(fixture("p5-multi"));
  await click(await find('[data-testid="clip-v1-clip"]'));
  await ctrlClickClip("v2-clip");
  assert.deepEqual(await selectedIds(), ["v1-clip", "v2-clip"]);
  assert.equal(await attr(await find('[data-testid="clip-v2-clip"]'), "data-primary"), "true");
  await dragClipToTrack("v1-clip", "v2");
  assert.equal(await clipTrack("v1-clip"), "v2");
  assert.equal(await clipTrack("v2-clip"), "v3");
  assert.deepEqual(await selectedIds(), ["v1-clip", "v2-clip"]);
  assert.equal(await attr(await find('[data-testid="clip-v2-clip"]'), "data-primary"), "true");
  assert.equal(await selectedTrackId(), "v3");
  await shortcut("z");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.equal(await clipTrack("v2-clip"), "v2");
  assert.equal(await selectedTrackId(), "v2");
  await shortcut("y");
  assert.equal(await clipTrack("v1-clip"), "v2");
  assert.equal(await clipTrack("v2-clip"), "v3");
  assert.equal(await selectedTrackId(), "v3");
  pass(gate);

  gate = "SELECTED_TRACK_AFTER_DROP";
  assert.equal(await selectedTrackId(), "v3");
  assert.deepEqual(await selectedIds(), ["v1-clip", "v2-clip"]);
  pass(gate);

  gate = "SELECTION_TARGET_CONTINUITY";
  assert.equal(await attr(await find('[data-testid="clip-v2-clip"]'), "data-primary"), "true");
  assert.equal(await selectedTrackId(), "v3");
  pass(gate);

  gate = "VERTICAL_DRAG_WITH_HORIZONTAL_DELTA";
  await load(fixture("p5-drag"));
  const dragStart = await startOf("v1-clip");
  await dragClipToTrack("v1-clip", "v2", 80);
  assert.equal(await clipTrack("v1-clip"), "v2");
  assert.ok(await startOf("v1-clip") > dragStart, "horizontal delta was not applied during cross-track drag");
  pass(gate);

  gate = "SNAP_DURING_CROSS_TRACK_DRAG";
  await load(fixture("p5-snap"));
  await click(await find('[data-testid="snap-toggle"]'));
  await dragClipToTrack("v1-clip", "v3", 88);
  assert.equal(await clipTrack("v1-clip"), "v3");
  assert.ok(Math.abs((await startOf("v1-clip")) - 2) < 0.02, `cross-track snap missed expected start 2s: ${await startOf("v1-clip")}`);
  pass(gate);

  gate = "WRONG_KIND_TARGET_FAIL_CLOSED";
  await load(fixture("p5-wrong-kind"));
  await dragClipToTrack("v1-clip", "a1");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.match(await errorText(), /CROSS_TRACK_TARGET_TRACK_KIND_MISMATCH/);
  pass(gate);

  gate = "DESTINATION_LOCKED_FAIL_CLOSED";
  await load(fixture("p5-locked"));
  await dragClipToTrack("v1-clip", "v-locked");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.match(await errorText(), /TRACK_LOCKED/);
  pass(gate);

  gate = "SOURCE_LOCKED_FAIL_CLOSED";
  const lockedSource = fixture("p5-source-locked");
  lockedSource.tracks.find((track) => track.id === "v1").locked = true;
  await load(lockedSource);
  await dragClipToTrack("v1-clip", "v2");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.match(await errorText(), /TRACK_LOCKED/);
  pass(gate);

  gate = "MIXED_VALID_INVALID_BATCH_ZERO_MUTATION";
  await load(fixture("p5-mixed-selection"));
  await click(await find('[data-testid="clip-v1-clip"]'));
  await ctrlClickClip("a1-clip");
  assert.deepEqual(await selectedIds(), ["a1-clip", "v1-clip"]);
  await dragClipToTrack("v1-clip", "v2");
  assert.equal(await clipTrack("v1-clip"), "v1");
  assert.equal(await clipTrack("a1-clip"), "a1");
  assert.match(await errorText(), /CROSS_TRACK_SELECTION_KIND_MISMATCH/);
  pass(gate);

  gate = "TRANSITION_CONFLICT_FAIL_CLOSED";
  await load(fixture("p5-transition", true));
  await click(await find('[data-testid="clip-fade"]'));
  await dragClipToTrack("fade", "v2");
  assert.equal(await clipTrack("fade"), "v1");
  assert.match(await errorText(), /CROSS_TRACK_TRANSITION_CONFLICT/);
  pass(gate);

  pass("REAL_TAURI_POINTER_GESTURE");
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
