import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
let sessionId = null;
let gate = "SESSION";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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
  for (let i = 0; i + 2 < buf.length; i += 3) if (buf[i] > 215 && buf[i + 1] > 215 && buf[i + 2] > 215) n++;
  return n;
}
function toneMagnitude(buf, frequency, sampleRate = 44100) {
  const n = Math.floor(buf.length / 2);
  let re = 0, im = 0;
  for (let i = 0; i < n; i++) {
    const sample = buf.readInt16LE(i * 2);
    const angle = 2 * Math.PI * frequency * i / sampleRate;
    re += sample * Math.cos(angle); im -= sample * Math.sin(angle);
  }
  return 2 * Math.hypot(re, im) / Math.max(1, n);
}
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "haios-p44-"));
  const red = path.join(dir, "red.mp4");
  const green = path.join(dir, "green.mp4");
  const blue = path.join(dir, "blue.mp4");
  const music = path.join(dir, "music.wav");
  const muted = path.join(dir, "muted.wav");
  const outPath = path.join(dir, "render.mp4");
  try {
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=red:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",red]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=green:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=660:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",green]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:r=30:d=2","-c:v","libx264","-pix_fmt","yuv420p",blue]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","sine=frequency=880:duration=2",music]);
    ffmpeg(["-y","-v","error","-f","lavfi","-i","sine=frequency=1000:duration=2",muted]);
    await createSession();
    gate = "HARNESS_SESSION_START"; pass(gate);
    const clip = (id, assetId, trackId, transform = { scale: 1, x: 0, y: 0, opacity: 1 }) => ({
      id, assetId, trackId, start: 0, inPoint: 0, duration: 2, playbackRate: 1, transform,
      effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn: null, audio: { gainDb: 0, muted: false },
    });
    const asset = (id, sourcePath, kind, hasAudio) => ({ id, name: path.basename(sourcePath), sourcePath, kind, durationSec: 2,
      width: kind === "video" ? 320 : undefined, height: kind === "video" ? 180 : undefined, fps: kind === "video" ? 30 : undefined,
      hasAudio, videoCodec: kind === "video" ? "h264" : undefined, audioCodec: hasAudio ? "aac" : undefined, createdAt: new Date(0).toISOString() });
    const project = {
      schemaVersion: 2, id: "p44-runtime", name: "P4.4 Runtime", createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
      assets: [asset("red", red, "video", true), asset("green", green, "video", true), asset("blue", blue, "video", false), asset("music", music, "audio", true), asset("muted", muted, "audio", true)],
      tracks: [
        { id: "back", kind: "video", clips: [clip("red-c", "red", "back")], captions: [], visible: true, muted: false, locked: false },
        { id: "mid-text", kind: "text", clips: [], captions: [{ id: "mid", text: "MID", start: 0, duration: 2, trackId: "mid-text", style: { x: 0.5, y: 0.5, fontSizePx: 120, color: "#FFFFFF", backgroundColor: "#FFFFFF", backgroundOpacity: 1 } }], visible: true, muted: false, locked: false },
        { id: "hidden", kind: "video", clips: [clip("green-c", "green", "hidden")], captions: [], visible: false, muted: false, locked: false },
        { id: "front", kind: "video", clips: [clip("blue-c", "blue", "front", { scale: 0.5, x: 0, y: 0, opacity: 1 })], captions: [], visible: true, muted: false, locked: false },
        { id: "top-text", kind: "text", clips: [], captions: [{ id: "top", text: "P4.4", start: 0, duration: 2, trackId: "top-text", style: { x: 0.5, y: 0.15, fontSizePx: 84, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.8 } }], visible: true, muted: false, locked: false },
        { id: "music", kind: "audio", clips: [clip("music-c", "music", "music")], captions: [], visible: true, muted: false, locked: false },
        { id: "muted-audio", kind: "audio", clips: [clip("muted-c", "muted", "muted-audio")], captions: [], visible: true, muted: true, locked: false },
      ], durationSec: 2, aspectRatio: "1920x1080",
    };
    gate = "TAURI_RENDER_JOB";
    const job = await tauriInvoke("hvs_render", { projectJson: JSON.stringify(project), outputPath: outPath, resolution: "1920x1080" });
    assert.match(String(job), /^job-/); pass(gate);
    gate = "RENDER_VERIFY";
    let ver = null;
    for (let i = 0; i < 100; i++) {
      if (fs.existsSync(outPath) && fs.statSync(outPath).size > 0) {
        ver = await tauriInvoke("verify_render", { outputPath: outPath, resolution: "1920x1080" }).catch(() => null);
        if (ver?.ok) break;
      }
      await sleep(250);
    }
    assert.equal(ver?.ok, true, ver?.error ?? "render did not verify"); pass(gate);
    const frame = ffmpeg(["-v","error","-ss","0.5","-i",outPath,"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"]);
    gate = "MULTITRACK_VISUAL_Z_ORDER";
    const corner = framePixel(frame, 120, 120);
    const center = framePixel(frame, 960, 540);
    assert.ok(corner[0] > corner[1] + 60 && corner[0] > corner[2] + 60, `corner must be red back layer: ${corner}`);
    assert.ok(center[2] > center[0] + 60 && center[2] > center[1] + 60, `center must be blue front layer over mid text: ${center}`);
    pass(gate);
    gate = "HIDDEN_VIDEO_EXCLUDED";
    assert.ok(corner[1] < corner[0] - 60, `hidden green layer must not cover back: ${corner}`); pass(gate);
    gate = "TEXT_LAYER_VISIBLE";
    assert.ok(countWhite(frame) > 500, "top text track must burn visible white pixels"); pass(gate);

    const pcm = ffmpeg(["-v","error","-ss","0.2","-t","1","-i",outPath,"-map","0:a:0","-ac","1","-ar","44100","-f","s16le","-"]);
    const p440 = toneMagnitude(pcm, 440), p660 = toneMagnitude(pcm, 660), p880 = toneMagnitude(pcm, 880), p1000 = toneMagnitude(pcm, 1000);
    gate = "EMBEDDED_HIDDEN_EXPLICIT_AUDIO_MIX";
    assert.ok(p440 > 500 && p660 > 500 && p880 > 200, `expected 440/660/880 tones: ${p440},${p660},${p880}`);
    pass(gate);
    gate = "MUTED_AUDIO_TRACK_EXCLUDED";
    assert.ok(p1000 < Math.min(p440, p660, p880) * 0.2, `muted 1000Hz tone leaked: ${p1000}`); pass(gate);
    gate = "REAL_TAURI_MULTITRACK_RENDER"; pass(gate);
  } finally {
    if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
