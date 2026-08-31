#!/usr/bin/env node
/** Mirror the exact pre-split state, measure c1's real box, try c1 clicks at offsets. */
import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const KEY = { CONTROL: "\uE009", ESCAPE: "\uE00C" };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
let sessionId = null;
async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, { method, headers: body === undefined ? undefined : { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${path} ${response.status}`);
  return payload.value;
}
async function createSession() {
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [] } } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}
const find = async (css) => (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
const findAll = async (css) => (await wd("POST", `/session/${sessionId}/elements`, { using: "css selector", value: css })).map(e => e[ELEMENT]);
const attr = async (id, n) => wd("GET", `/session/${sessionId}/element/${id}/attribute/${n}`);
const rect = async (id) => wd("GET", `/session/${sessionId}/element/${id}/rect`);
const perform = async (a) => { await wd("POST", `/session/${sessionId}/actions`, { actions: a }); await wd("DELETE", `/session/${sessionId}/actions`); await sleep(100); };
const press = async (k) => perform([{ type: "key", id: "k", actions: [{ type: "keyDown", value: k }, { type: "keyUp", value: k }] }]);
const shortcut = async (k) => perform([{ type: "key", id: "k", actions: [{ type: "keyDown", value: KEY.CONTROL }, { type: "keyDown", value: k }, { type: "keyUp", value: k }, { type: "keyUp", value: KEY.CONTROL }] }]);
async function ctrlClick(id, offsetX = 0) {
  const b = await rect(id);
  const vx = b.x + offsetX, vy = b.y + b.height / 2;
  await perform([{ type: "key", id: "kb", actions: [{ type: "keyDown", value: KEY.CONTROL }] },
    { type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [{ type: "pointerMove", x: Math.round(vx), y: Math.round(vy) }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }] },
    { type: "key", id: "kb", actions: [{ type: "keyUp", value: KEY.CONTROL }] }]);
  await sleep(140);
}
(async () => {
  await createSession();
  await sleep(2500);
  await shortcut("a"); await sleep(140);
  await shortcut("d"); await sleep(220);
  await press(KEY.ESCAPE); await sleep(160);
  const ids = await findAll(".clip");
  console.log("NCLIPS=" + ids.length);
  for (const el of ids) {
    const b = await rect(el);
    const tid = await attr(el, "data-testid");
    const sel = await attr(el, "data-selected");
    console.log(`BOX ${tid} x=${b.x.toFixed(0)} w=${b.width.toFixed(0)} right=${((b.x + b.width)).toFixed(0)} y=${b.y.toFixed(0)} sel=${sel}`);
  }
  const c0 = await find('[data-testid="clip-c0"]');
  const c1 = await find('[data-testid="clip-c1"]');
  const b0 = await rect(c0), b1 = await rect(c1);
  console.log("C0_LEFT=" + b0.x.toFixed(0) + " C1_LEFT=" + b1.x.toFixed(0) + " H=" + b1.height.toFixed(0));
  for (const off of [40, 200, 320, 440, 600, 720]) {
    await press(KEY.ESCAPE); await sleep(90);
    await ctrlClick(c0, 40); await sleep(90);
    await ctrlClick(c1, off);
    const c0s = await attr(c0, "data-selected"), c1s = await attr(c1, "data-selected");
    console.log(`OFFSET ${off} clickX=${(b1.x + off).toFixed(0)} -> c0=${c0s} c1=${c1s}`);
  }
  await wd("DELETE", `/session/${sessionId}`);
  process.exit(0);
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
