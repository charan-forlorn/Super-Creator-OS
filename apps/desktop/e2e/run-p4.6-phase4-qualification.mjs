import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "HARNESS_SESSION_START";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const pass = (name) => console.log(`${name}=PASS`);

async function wd(method, urlPath, body) {
  const res = await fetch(`${DRIVER}${urlPath}`, { method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${urlPath} failed ${res.status}`);
  return payload.value;
}
async function createSession() {
  const shims = "C:/Users/chara/scoop/shims";
  const envPath = (process.env.PATH || "").includes(shims) ? process.env.PATH : `${shims};${process.env.PATH || ""}`;
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: {
    browserName: "webview2", "tauri:options": { application: APP, env: { PATH: envPath } },
  } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}
async function findAll(css) {
  return (await wd("POST", `/session/${sessionId}/elements`, { using: "css selector", value: css }))
    .map((entry) => entry[ELEMENT]);
}
async function attr(id, name) {
  return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`);
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
  const i = (y * width + x) * 3;
  return [buf[i], buf[i + 1], buf[i + 2]];
}
function countWhite(buf) {
  let n = 0;
  for (let i = 0; i + 2 < buf.length; i += 3) {
    if (buf[i] > 215 && buf[i + 1] > 215 && buf[i + 2] > 215) n += 1;
  }
  return n;
}
function toneMagnitude(buf, frequency, sampleRate = 44100) {
  const n = Math.floor(buf.length / 2);
  let re = 0, im = 0;
  for (let i = 0; i < n; i += 1) {
    const sample = buf.readInt16LE(i * 2);
    const angle = 2 * Math.PI * frequency * i / sampleRate;
    re += sample * Math.cos(angle); im -= sample * Math.sin(angle);
  }
  return 2 * Math.hypot(re, im) / Math.max(1, n);
}
async function previewSignature() {
  const layerEls = await findAll("[data-preview-layer]");
  const layers = [];
  for (const id of layerEls) layers.push(await attr(id, "data-preview-layer"));
  const audioEls = await findAll("[data-preview-audio]");
  const audio = [];
  for (const id of audioEls) audio.push(await attr(id, "data-preview-audio"));
  const captionEls = await findAll("[data-preview-caption]");
  const captions = [];
  for (const id of captionEls) captions.push(await attr(id, "data-preview-caption"));
  return { layers, audio, captions };
}

function clip(id, assetId, trackId, transform = { scale: 1, x: 0, y: 0, opacity: 1 }) {
  return { id, assetId, trackId, start: 0, inPoint: 0, duration: 2, playbackRate: 1, transform,
    effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn: null,
    audio: { gainDb: 0, muted: false } };
}
function asset(id, sourcePath, kind, hasAudio) {
  return { id, name: path.basename(sourcePath), sourcePath, kind, durationSec: 2,
    width: kind === "video" ? 320 : undefined, height: kind === "video" ? 180 : undefined,
    fps: kind === "video" ? 30 : undefined, hasAudio,
    videoCodec: kind === "video" ? "h264" : undefined,
    audioCodec: hasAudio ? "aac" : undefined, createdAt: new Date(0).toISOString() };
}
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "haios-p46-"));
  const red = path.join(dir, "red.mp4");
  const green = path.join(dir, "green.mp4");
  const blue = path.join(dir, "blue.mp4");
  const music = path.join(dir, "music.wav");
  const outPath = path.join(dir, "phase4.mp4");
  try {
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=red:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",red]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=green:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=660:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",green]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=550:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",blue]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","sine=frequency=880:duration=2",music]);
    await createSession();
    pass(gate);
    const project = {
      schemaVersion: 2, id: "p46-runtime", name: "P4.6 Phase 4 Qualification",
      createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
      assets: [
        asset("p43-back-asset", red, "video", true),
        asset("p43-hidden-asset", green, "video", true),
        asset("p43-front-asset", blue, "video", true),
        asset("p43-music-asset", music, "audio", true),
      ],
      tracks: [
        { id: "v-back", kind: "video", clips: [clip("p43-back", "p43-back-asset", "v-back")], captions: [], visible: true, muted: false, locked: false },
        { id: "v-hidden", kind: "video", clips: [clip("p43-hidden", "p43-hidden-asset", "v-hidden")], captions: [], visible: false, muted: true, locked: false },
        { id: "v-front", kind: "video", clips: [clip("p43-front", "p43-front-asset", "v-front", { scale: 0.5, x: 0, y: 0, opacity: 1 })], captions: [], visible: true, muted: false, locked: false },
        { id: "text-front", kind: "text", clips: [], captions: [{ id: "p43-caption", text: "P4.6", start: 0, duration: 2, trackId: "text-front", style: { x: 0.5, y: 0.15, fontSizePx: 84, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.8 } }], visible: true, muted: false, locked: false },
        { id: "a-music", kind: "audio", clips: [clip("p43-music", "p43-music-asset", "a-music")], captions: [], visible: true, muted: false, locked: false },
      ],
      durationSec: 2, aspectRatio: "1920x1080",
    };
    const loadedProjectId = await wd("POST", `/session/${sessionId}/execute/sync`, {
      script: `window.dispatchEvent(new CustomEvent("haios-e2e-load-project", { detail: arguments[0] }));
        return document.documentElement.getAttribute("data-e2e-project-loaded");`,
      args: [project],
    });
    assert.equal(loadedProjectId, project.id);
    await sleep(50);
    gate = "PREVIEW_COMPOSITION_SIGNATURE";
    const signature = await previewSignature();
    assert.deepEqual(signature.layers, ["v-back", "v-front"]);
    assert.deepEqual(signature.audio.sort(), ["p43-back", "p43-front", "p43-music"].sort());
    assert.deepEqual(signature.captions, ["p43-caption"]);
    pass(gate);
    gate = "SAVE_REOPEN_V2";
    const projectPath = path.join(dir, "phase4-roundtrip.haip.json");
    await tauriInvoke("project_save", { path: projectPath, projectJson: JSON.stringify(project) });
    const reopened = JSON.parse(await tauriInvoke("project_open", { path: projectPath }));
    assert.deepEqual(reopened, JSON.parse(JSON.stringify(project)));
    pass(gate);

    gate = "EXPORT_COMPOSITION_RUNTIME";
    const job = await tauriInvoke("hvs_render", {
      projectJson: JSON.stringify(project), outputPath: outPath, resolution: "1920x1080",
    });
    assert.match(String(job), /^job-/);
    let verified = null;
    for (let i = 0; i < 100; i += 1) {
      if (fs.existsSync(outPath) && fs.statSync(outPath).size > 0) {
        verified = await tauriInvoke("verify_render", { outputPath: outPath, resolution: "1920x1080" }).catch(() => null);
        if (verified?.ok) break;
      }
      await sleep(250);
    }
    assert.equal(verified?.ok, true, verified?.error ?? "render did not verify");
    pass(gate);

    const frame = ffmpeg(["-v","error","-ss","0.5","-i",outPath,"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"]);
    gate = "PREVIEW_EXPORT_FRAME_PARITY";
    const corner = framePixel(frame, 120, 120);
    const center = framePixel(frame, 960, 540);
    assert.ok(corner[0] > corner[1] + 60 && corner[0] > corner[2] + 60, `back layer missing: ${corner}`);
    assert.ok(center[2] > center[0] + 60 && center[2] > center[1] + 60, `front layer missing: ${center}`);
    assert.ok(countWhite(frame) > 500, "caption layer missing");
    pass(gate);
    const pcm = ffmpeg(["-v","error","-ss","0.2","-t","1","-i",outPath,"-map","0:a:0","-ac","1","-ar","44100","-f","s16le","-"]);
    const p440 = toneMagnitude(pcm, 440);
    const p550 = toneMagnitude(pcm, 550);
    const p660 = toneMagnitude(pcm, 660);
    const p880 = toneMagnitude(pcm, 880);
    gate = "PREVIEW_EXPORT_AUDIO_PARITY";
    assert.ok(p440 > 400 && p550 > 400 && p880 > 200, `expected preview audio set in export: ${p440},${p550},${p880}`);
    assert.ok(p660 < Math.min(p440, p550, p880) * 0.2, `muted hidden audio leaked: ${p660}`);
    pass(gate);

    gate = "PHASE4_CROSS_RUNTIME_PARITY";
    assert.deepEqual(signature.layers, ["v-back", "v-front"]);
    assert.deepEqual(signature.audio.sort(), ["p43-back", "p43-front", "p43-music"].sort());
    pass(gate);
  } finally {
    if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

try { await main(); }
catch (error) {
  console.error(`${gate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
}
