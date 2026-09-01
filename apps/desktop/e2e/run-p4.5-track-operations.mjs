#!/usr/bin/env node
import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wd(method, path, body) {
  const res = await fetch(`${DRIVER}${path}`, { method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed ${res.status}`);
  return payload.value;
}
async function find(css) { return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT]; }
async function maybeFind(css) { try { return await find(css); } catch { return null; } }
async function waitFor(css, timeoutMs = 6000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { const id = await maybeFind(css); if (id) return id; await sleep(50); }
  throw new Error(`${css} not found`);
}
async function click(id) { await wd("POST", `/session/${sessionId}/element/${id}/click`, {}); await sleep(120); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function exec(script, args = []) { return wd("POST", `/session/${sessionId}/execute/sync`, { script, args }); }
function pass(name) { console.log(`${name}=PASS`); }
async function trackIds() {
  return exec(`return Array.from(document.querySelectorAll('[data-testid^="track-select-"]')).map(el=>el.getAttribute('data-testid').replace('track-select-',''));`);
}
async function targetText() {
  return exec(`return document.querySelector('[data-testid="selected-track-target"]')?.textContent || '';`);
}
async function selectedTrackClipCount() {
  return exec(`const row=document.querySelector('.track.target-selected'); return row ? row.querySelectorAll('.clip').length : -1;`);
}
async function firstTrackId() {
  return exec(`const row=document.querySelector('.track [data-testid^="track-row-"]'); return row ? row.getAttribute('data-testid').replace('track-row-','') : null;`);
}

async function main() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
  await waitFor('[data-testid="track-add-video"]');
  pass(gate);

  gate = "TRACK_TARGET_SELECTION";
  const existing = await waitFor('[data-testid="track-select-track-video-1"]');
  await click(existing);
  assert.match(await targetText(), /track-video-1/);
  assert.equal(await attr(existing, "data-selected"), "true");
  pass(gate);
  gate = "ADD_VIDEO_TRACK";
  const before = await trackIds();
  await click(await find('[data-testid="track-add-video"]'));
  const after = await trackIds();
  const newVideo = after.find((id) => !before.includes(id));
  assert.ok(newVideo && newVideo.startsWith("track-video-"), `new video track missing: ${after}`);
  assert.match(await targetText(), new RegExp(newVideo));
  assert.equal(await attr(await find(`[data-testid="track-select-${newVideo}"]`), "data-selected"), "true");
  pass(gate);

  gate = "EXPLICIT_TARGET_INSERT";
  await click(await waitFor('[data-testid="media-item-asset-fixture"]'));
  const beforeClips = await selectedTrackClipCount();
  await click(await waitFor('[data-testid="insert-edit"]'));
  assert.equal(await selectedTrackClipCount(), beforeClips + 1);
  pass(gate);

  gate = "TRACK_CONTROL_TOGGLES";
  const vis = await find(`[data-testid="track-visible-${newVideo}"]`);
  const mute = await find(`[data-testid="track-muted-${newVideo}"]`);
  const lock = await find(`[data-testid="track-locked-${newVideo}"]`);
  assert.equal(await attr(vis, "aria-pressed"), "true");
  await click(vis); assert.equal(await attr(await find(`[data-testid="track-visible-${newVideo}"]`), "aria-pressed"), "false");
  await click(mute); assert.equal(await attr(await find(`[data-testid="track-muted-${newVideo}"]`), "aria-pressed"), "true");
  await click(lock); assert.equal(await attr(await find(`[data-testid="track-locked-${newVideo}"]`), "aria-pressed"), "true");
  pass(gate);
  gate = "TRACK_REORDER_AND_REMOVE";
  await click(await find(`[data-testid="track-locked-${newVideo}"]`));
  assert.equal(await attr(await find(`[data-testid="track-locked-${newVideo}"]`), "aria-pressed"), "false");
  await click(await find('[data-testid="track-move-up"]'));
  assert.equal(await firstTrackId(), newVideo);
  await click(await find('[data-testid="track-remove-selected"]'));
  assert.equal(await maybeFind(`[data-testid="track-select-${newVideo}"]`), null);
  assert.match(await targetText(), /none/);
  pass(gate);

  gate = "ADD_AUDIO_TEXT_TRACKS";
  const beforeAudioText = await trackIds();
  await click(await find('[data-testid="track-add-audio"]'));
  const afterAudio = await trackIds();
  const newAudio = afterAudio.find((id) => !beforeAudioText.includes(id));
  assert.ok(newAudio?.startsWith("track-audio-"));
  await click(await find('[data-testid="track-add-text"]'));
  const afterText = await trackIds();
  const newText = afterText.find((id) => !afterAudio.includes(id));
  assert.ok(newText?.startsWith("track-text-"));
  assert.match(await targetText(), new RegExp(newText));
  pass(gate);

  gate = "REAL_GUI_TRACK_OPERATIONS";
  pass(gate);
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
