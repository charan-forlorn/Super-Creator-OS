#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "SESSION";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function wd(method, path, body) {
  const res = await fetch(`${DRIVER}${path}`, {
    method, headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed ${res.status}`);
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
async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function prop(id, name) {
  return wd("GET", `/session/${sessionId}/element/${id}/property/${name}`);
}
async function rect(id) {
  return wd("GET", `/session/${sessionId}/element/${id}/rect`);
}
async function click(id) {
  await wd("POST", `/session/${sessionId}/execute/sync`, {
    script: "arguments[0].scrollIntoView({block:'center',inline:'nearest'});",
    args: [{ [ELEMENT]: id }],
  });
  await sleep(80);
  await wd("POST", `/session/${sessionId}/element/${id}/click`, {});
  await sleep(150);
}
async function pointerClickClip(id) {
  const el = await find(`[data-testid="clip-${id}"]`);
  const b = await rect(el);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{
    type: "pointer", id: "mouse", parameters: { pointerType: "mouse" },
    actions: [
      { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + 35), y: Math.round(b.y + b.height / 2) },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
    ],
  }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(180);
}
function pass(name) { console.log(`${name}=PASS`); }
async function main() {
  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);
  await pointerClickClip("c0");

  const video = await find("video.preview-video");
  let audio = await find('audio[data-preview-audio="c0"]');
  gate = "SOURCE_AUDIO_DEFAULT_UNMUTED";
  assert.equal(await prop(video, "muted"), true, "visual video stays muted to avoid double-play");
  assert.equal(await prop(audio, "muted"), false, "dedicated audio runtime is audible by default");
  assert.ok(Math.abs(Number(await prop(audio, "volume")) - 1) < 0.001);
  pass(gate);

  gate = "AUDIO_CONTROLS_VISIBLE";
  const mute = await find('[data-testid="audio-muted"]');
  const gain = await find('[data-testid="audio-gain"]');
  assert.ok(mute && gain); pass(gate);

  gate = "AUDIO_MUTE_PREVIEW";
  await click(mute);
  let mutedAudioPresent = true;
  try { await find('audio[data-preview-audio="c0"]'); } catch { mutedAudioPresent = false; }
  assert.equal(mutedAudioPresent, false, "muted clip must leave the effective audio mix");
  assert.equal(await prop(video, "muted"), true);
  pass(gate);
  gate = "AUDIO_UNDO_RESTORE";
  await click(await find('button[title="Ctrl+Z"]'));
  audio = await find('audio[data-preview-audio="c0"]');
  assert.equal(await prop(audio, "muted"), false);
  pass(gate);

  gate = "AUDIO_GAIN_PREVIEW";
  await wd("POST", `/session/${sessionId}/element/${gain}/clear`, {});
  await wd("POST", `/session/${sessionId}/element/${gain}/value`, { text: "-12", value: ["-", "1", "2"] });
  await sleep(250);
  assert.equal(String(await prop(gain, "value")), "-12", "gain control must commit -12 dB");
  const volume = Number(await prop(audio, "volume"));
  assert.ok(Math.abs(volume - Math.pow(10, -12 / 20)) < 0.01, `expected -12 dB volume, got ${volume}`);
  pass(gate);

  gate = "REAL_GUI_RUNTIME";
  assert.ok((await wd("GET", `/session/${sessionId}/title`)).startsWith("HAIOS AI Video Studio"));
  pass(gate);
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
