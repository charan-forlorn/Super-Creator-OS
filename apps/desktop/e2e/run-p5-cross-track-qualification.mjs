#!/usr/bin/env node
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const DRIVER = process.env.HAIOS_WEBDRIVER_URL ?? "http://127.0.0.1:4444";
const APP = process.env.HAIOS_APP_PATH;
assert.ok(APP, "HAIOS_APP_PATH is required for Phase 5 runtime qualification");
assert.ok(fs.existsSync(APP), `HAIOS_APP_PATH does not exist: ${APP}`);
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const pass = (name) => console.log(`${name}=PASS`);

async function wd(method, urlPath, body) {
  const response = await fetch(`${DRIVER}${urlPath}`, {
    method, headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${urlPath} failed ${response.status}`);
  return payload.value;
}
async function createSession() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, args: [] },
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
async function click(id) { await wd("POST", `/session/${sessionId}/element/${id}/click`, {}); await sleep(140); }
async function exec(script, args = []) {
  return wd("POST", `/session/${sessionId}/execute/sync`, { script, args });
}
async function perform(actions) {
  await wd("POST", `/session/${sessionId}/actions`, { actions });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(150);
}
async function dragClipToTrack(clipId, targetTrackId, dx = 0) {
  const clipElement = await find(`[data-testid="clip-${clipId}"]`);
  const laneElement = await find(`[data-track-id="${targetTrackId}"] .track-lane`);
  const offsetX = await exec(`const c=document.querySelector(arguments[0]).getBoundingClientRect();
    const l=document.querySelector(arguments[1]).getBoundingClientRect();
    return c.left+c.width/2+arguments[2]-(l.left+l.width/2);`, [
    `[data-testid="clip-${clipId}"]`, `[data-track-id="${targetTrackId}"] .track-lane`, dx,
  ]);
  await perform([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: { [ELEMENT]: clipElement }, x: 0, y: 0 },
    { type: "pointerDown", button: 0 },
    { type: "pointerMove", duration: 180, origin: { [ELEMENT]: laneElement }, x: Math.round(offsetX), y: 0 },
    { type: "pointerUp", button: 0 },
  ] }]);
}
async function tauriInvoke(command, args) {
  const script = `const done=arguments[arguments.length-1];
    window.__TAURI_INTERNALS__.invoke(arguments[0], arguments[1])
      .then(v=>done({ok:true,value:v})).catch(e=>done({ok:false,error:String(e)}));`;
  const result = await wd("POST", `/session/${sessionId}/execute/async`, { script, args: [command, args] });
  if (!result?.ok) throw new Error(result?.error ?? `${command} failed`);
  return result.value;
}
function ffmpeg(args) {
  const out = spawnSync("ffmpeg", args, { encoding: null, maxBuffer: 128 * 1024 * 1024 });
  if (out.status !== 0) throw new Error(`ffmpeg failed: ${String(out.stderr)}`);
  return out.stdout;
}
function framePixel(buf, x, y, width = 1920) {
  const index = (y * width + x) * 3;
  return [buf[index], buf[index + 1], buf[index + 2]];
}
function maximumAbsolutePcmSample(buf) {
  let maximum = 0;
  for (let index = 0; index + 1 < buf.length; index += 2) {
    maximum = Math.max(maximum, Math.abs(buf.readInt16LE(index)));
  }
  return maximum;
}
async function previewLayers() {
  return exec(`return Array.from(document.querySelectorAll('[data-preview-layer]'))
    .map((el) => el.getAttribute('data-preview-layer'));`);
}
async function currentProject() {
  const json = await exec(`window.dispatchEvent(new Event('haios-e2e-request-project'));
    return document.documentElement.getAttribute('data-e2e-project-json');`);
  assert.ok(json, "E2E project snapshot was not exposed by the test-only entry");
  return JSON.parse(json);
}
function clip(id, assetId, trackId) {
  return {
    id, assetId, trackId, start: 0, inPoint: 0, duration: 2, playbackRate: 1,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    effects: { brightness: 0, contrast: 1, saturation: 1 },
    transitionIn: null, audio: { gainDb: 0, muted: false },
  };
}
function videoAsset(id, sourcePath) {
  return {
    id, name: path.basename(sourcePath), sourcePath, kind: "video", durationSec: 2,
    width: 320, height: 180, fps: 30, hasAudio: false, videoCodec: "h264",
    audioCodec: null, createdAt: new Date(0).toISOString(),
  };
}
function audioAsset(id, sourcePath) {
  return {
    id, name: path.basename(sourcePath), sourcePath, kind: "audio", durationSec: 2,
    hasAudio: true, audioCodec: "aac", createdAt: new Date(0).toISOString(),
  };
}
async function load(project) {
  const loaded = await exec(`window.dispatchEvent(new CustomEvent('haios-e2e-load-project',
    { detail: arguments[0] }));
    return document.documentElement.getAttribute('data-e2e-project-loaded');`, [project]);
  assert.equal(loaded, project.id);
  await waitFor('[data-testid="clip-moving"]');
  await sleep(150);
}
async function clipTrack(clipId) {
  return exec(`return document.querySelector(arguments[0])?.closest('[data-track-id]')
    ?.getAttribute('data-track-id') ?? null;`, [`[data-testid="clip-${clipId}"]`]);
}
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "haios-p5-runtime-"));
  const blue = path.join(dir, "base-blue.mp4");
  const red = path.join(dir, "moving-red.mp4");
  const tone = path.join(dir, "destination-tone.m4a");
  const output = path.join(dir, "phase5-after-move.mp4");
  const savedPath = path.join(dir, "phase5-after-move.haip.json");
  try {
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:r=30:d=2",
      "-c:v","libx264","-pix_fmt","yuv420p",blue]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=red:s=320x180:r=30:d=2",
      "-c:v","libx264","-pix_fmt","yuv420p",red]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","sine=frequency=880:sample_rate=48000:duration=2",
      "-c:a","aac",tone]);
    await createSession();
    pass(gate);
    const project = {
      schemaVersion: 2, id: "p5-runtime", name: "Phase 5 Runtime Qualification",
      createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
      assets: [videoAsset("base-asset", blue), videoAsset("moving-asset", red), audioAsset("tone-asset", tone)],
      tracks: [
        { id: "v-base", kind: "video", clips: [clip("base", "base-asset", "v-base")], captions: [], visible: true, muted: false, locked: false },
        { id: "v-source", kind: "video", clips: [clip("moving", "moving-asset", "v-source")], captions: [], visible: true, muted: false, locked: false },
        { id: "v-hidden", kind: "video", clips: [], captions: [], visible: false, muted: false, locked: false },
        { id: "a-source", kind: "audio", clips: [clip("tone", "tone-asset", "a-source")], captions: [], visible: true, muted: true, locked: false },
        { id: "a-destination", kind: "audio", clips: [], captions: [], visible: true, muted: false, locked: false },
      ],
      durationSec: 2, aspectRatio: "1920x1080",
    };
    await load(project);
    assert.deepEqual(await previewLayers(), ["v-base", "v-source"]);
    await dragClipToTrack("moving", "v-hidden");
    assert.equal(await clipTrack("moving"), "v-hidden");
    await dragClipToTrack("tone", "a-destination");
    assert.equal(await clipTrack("tone"), "a-destination");

    gate = "PREVIEW_AFTER_MOVE";
    assert.deepEqual(await previewLayers(), ["v-base"]);
    pass(gate);

    const moved = await currentProject();
    const movedClip = moved.tracks.find((track) => track.id === "v-hidden")
      ?.clips.find((entry) => entry.id === "moving");
    assert.equal(movedClip?.trackId, "v-hidden");
    assert.equal(moved.tracks.find((track) => track.id === "v-source")?.clips.length, 0);
    const movedTone = moved.tracks.find((track) => track.id === "a-destination")
      ?.clips.filter((entry) => entry.id === "tone") ?? [];
    assert.equal(movedTone.length, 1, "moved audio must occur exactly once in the destination track");
    assert.equal(movedTone[0]?.trackId, "a-destination");
    assert.equal(moved.tracks.find((track) => track.id === "a-source")?.clips.filter((entry) => entry.id === "tone").length, 0);

    gate = "SAVE_REOPEN_AFTER_MOVE";
    await tauriInvoke("project_save", { path: savedPath, projectJson: JSON.stringify(moved) });
    const reopened = JSON.parse(await tauriInvoke("project_open", { path: savedPath }));
    assert.deepEqual(reopened, moved);
    pass(gate);

    gate = "EXPORT_AFTER_MOVE";
    const job = await tauriInvoke("hvs_render", {
      projectJson: JSON.stringify(moved), outputPath: output, resolution: "1920x1080",
    });
    assert.match(String(job), /^job-/);
    let verified = null;
    for (let i = 0; i < 100; i += 1) {
      if (fs.existsSync(output) && fs.statSync(output).size > 0) {
        verified = await tauriInvoke("verify_render", { outputPath: output, resolution: "1920x1080" }).catch(() => null);
        if (verified?.ok) break;
      }
      await sleep(250);
    }
    assert.equal(verified?.ok, true, verified?.error ?? "render did not verify");
    const frame = ffmpeg(["-v","error","-ss","0.5","-i",output,
      "-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"]);
    const center = framePixel(frame, 960, 540);
    assert.ok(center[2] > center[0] + 60 && center[2] > center[1] + 60,
      `hidden moved layer leaked into export: ${center}`);
    pass(gate);

    gate = "DESTINATION_AUDIO_CONTRIBUTION_NO_DUPLICATION";
    const pcm = ffmpeg(["-v", "error", "-ss", "0.5", "-i", output, "-t", "0.5",
      "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", "48000", "-"]);
    assert.ok(maximumAbsolutePcmSample(pcm) > 500,
      "audio moved from muted source to unmuted destination did not contribute to export");
    assert.equal(moved.tracks.flatMap((track) => track.clips).filter((entry) => entry.id === "tone").length, 1,
      "moved audio was duplicated in the canonical Project");
    pass(gate);

    gate = "PREVIEW_EXPORT_AFTER_MOVE_PARITY";
    assert.deepEqual(await previewLayers(), ["v-base"]);
    assert.equal(reopened.tracks.find((track) => track.id === "v-hidden")
      ?.clips.find((entry) => entry.id === "moving")?.trackId, "v-hidden");
    assert.equal(reopened.tracks.find((track) => track.id === "a-destination")
      ?.clips.filter((entry) => entry.id === "tone").length, 1);
    pass(gate);
  } finally {
    if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
try {
  await main();
} catch (error) {
  console.error(`${gate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
}
