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
function centerRgb(buf, w, h) {
  const i = (Math.floor(h / 2) * w + Math.floor(w / 2)) * 3;
  return [buf[i], buf[i + 1], buf[i + 2]];
}
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "haios-r29-"));
  const src = path.join(dir, "red-tone.mp4");
  const outPath = path.join(dir, "render.mp4");
  try {
    ffmpeg(["-y","-v","error","-f","lavfi","-i","color=c=red:s=320x180:r=30:d=2","-f","lavfi","-i","sine=frequency=440:duration=2","-shortest","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",src]);
    await createSession();
    gate = "HARNESS_SESSION_START"; pass(gate);
    const project = {
      schemaVersion: 1, id: "r29-runtime", name: "R2.9 Runtime", createdAt: new Date(0).toISOString(), updatedAt: new Date(0).toISOString(),
      assets: [{ id: "a0", name: "red-tone.mp4", sourcePath: src, kind: "video", durationSec: 2,
        width: 320, height: 180, fps: 30, hasAudio: true, videoCodec: "h264", audioCodec: "aac", createdAt: new Date(0).toISOString() }],
      tracks: [{ id: "v1", kind: "video", clips: [{ id: "c0", assetId: "a0", inPoint: 0, duration: 2, start: 0,
        trackId: "v1", transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false },
        effects: { brightness: 0, contrast: 1, saturation: 0 } }], captions: [] }],
      durationSec: 2, aspectRatio: "1920x1080",
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
    gate = "EFFECTS_RENDER_FIDELITY";
    const frame = ffmpeg(["-v","error","-ss","0.8","-i",outPath,"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-"]);
    const [r,g,b] = centerRgb(frame, 1920, 1080);
    assert.ok(Math.abs(r-g) < 8 && Math.abs(g-b) < 8, `saturation=0 output must be grayscale at center: ${r},${g},${b}`);
    pass(gate);
    gate = "REAL_TAURI_RENDER_RUNTIME"; pass(gate);
  } finally {
    if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
