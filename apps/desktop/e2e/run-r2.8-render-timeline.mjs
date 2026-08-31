#!/usr/bin/env node
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
function pass(name) { console.log(`${name}=PASS`); }

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
  const out = spawnSync("ffmpeg", args, { encoding: null, maxBuffer: 64 * 1024 * 1024 });
  if (out.status !== 0) throw new Error(`ffmpeg failed: ${String(out.stderr)}`);
  return out.stdout;
}
function maxSample(buf) {
  let max = 0;
  for (let i = 0; i + 1 < buf.length; i += 2) max = Math.max(max, Math.abs(buf.readInt16LE(i)));
  return max;
}
function countWhite(buf) {
  let n = 0;
  for (let i = 0; i + 2 < buf.length; i += 3) {
    if (buf[i] > 200 && buf[i + 1] > 200 && buf[i + 2] > 200) n++;
  }
  return n;
}
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "haios-r28-"));
  const src = path.join(dir, "blue-tone.mp4");
  const outPath = path.join(dir, "render.mp4");
  try {
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=blue:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",src]);
    await createSession();
    gate = "HARNESS_SESSION_START"; pass(gate);
    const project = {
      schemaVersion: 1, id: "r28-runtime", name: "R2.8 Runtime", createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
      assets: [{ id: "a0", name: "blue-tone.mp4", sourcePath: src, kind: "video", durationSec: 2,
        width: 320, height: 180, fps: 30, hasAudio: true, videoCodec: "h264", audioCodec: "aac", createdAt: new Date(0).toISOString() }],
      tracks: [
        { id: "v1", kind: "video", clips: [{ id: "c0", assetId: "a0", inPoint: 0, duration: 2, start: 1,
          trackId: "v1", transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false } }], captions: [] },
        { id: "t1", kind: "text", clips: [], captions: [{ id: "cap0", text: "ไทย R2.8", start: 1.5, duration: 0.75, trackId: "t1",
          style: { fontSizePx: 72, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.8, x: 0.5, y: 0.5 } }] },
      ], durationSec: 3, aspectRatio: "1920x1080",
    };
    gate = "TAURI_RENDER_JOB";
    const job = await tauriInvoke("hvs_render", { projectJson: JSON.stringify(project), outputPath: outPath, resolution: "1920x1080" });
    assert.match(String(job), /^job-/); pass(gate);

    gate = "RENDER_VERIFY";
    let ver = null;
    for (let i = 0; i < 80; i++) {
      if (fs.existsSync(outPath) && fs.statSync(outPath).size > 0) {
        ver = await tauriInvoke("verify_render", { outputPath: outPath, resolution: "1920x1080" }).catch(() => null);
        if (ver?.ok) break;
      }
      await sleep(250);
    }
    assert.equal(ver?.ok, true, ver?.error ?? "render did not verify"); pass(gate);
    const frameAt = (sec) => ffmpeg(["-v","error","-ss",String(sec),"-i",outPath,"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"]);
    const pre = frameAt(0.5);
    const active = frameAt(1.2);
    const caption = frameAt(1.8);
    gate = "TIMELINE_VIDEO_GAP";
    assert.ok(pre.every((b) => b < 20), "pre-start frame must be black"); pass(gate);
    gate = "TIMELINE_VIDEO_ACTIVE";
    assert.ok(active.some((b) => b > 40), "active clip must contain blue pixels"); pass(gate);
    gate = "CAPTION_BURN_IN";
    assert.ok(countWhite(caption) > countWhite(active) + 50, "caption frame must add white text pixels"); pass(gate);

    const audioSlice = (start) => ffmpeg(["-v","error","-ss",String(start),"-t","0.7","-i",outPath,"-map","0:a:0","-ac","1","-ar","44100","-f","s16le","-"]);
    gate = "TIMELINE_AUDIO_GAP";
    assert.ok(maxSample(audioSlice(0.1)) < 250, "pre-start audio must be near-silent"); pass(gate);
    gate = "TIMELINE_AUDIO_ACTIVE";
    assert.ok(maxSample(audioSlice(1.2)) > 500, "delayed source audio must be audible"); pass(gate);
    gate = "REAL_TAURI_RENDER_RUNTIME"; pass(gate);
  } finally {
    if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
