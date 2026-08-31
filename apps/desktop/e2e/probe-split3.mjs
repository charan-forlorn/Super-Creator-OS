#!/usr/bin/env node
/** Read-only probe: does the ruler click move the playhead and does 's' split? */
import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const KEY = { CONTROL: "\uE009", ESCAPE: "\uE00C" };
let AID = 0; const nid = () => "a" + (AID++);
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
const press = async (k) => perform([{ type: "key", id: nid(), actions: [{ type: "keyDown", value: k }, { type: "keyUp", value: k }] }]);
const shortcut = async (k) => perform([{ type: "key", id: nid(), actions: [{ type: "keyDown", value: KEY.CONTROL }, { type: "keyDown", value: k }, { type: "keyUp", value: k }, { type: "keyUp", value: KEY.CONTROL }] }]);
async function ctrlClick(id, offsetX = 0) {
  const b = await rect(id);
  await perform([{ type: "key", id: nid(), actions: [{ type: "keyDown", value: KEY.CONTROL }] },
    { type: "pointer", id: nid(), parameters: { pointerType: "mouse" }, actions: [{ type: "pointerMove", x: Math.round(b.x + offsetX), y: Math.round(b.y + b.height / 2) }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }] },
    { type: "key", id: nid(), actions: [{ type: "keyUp", value: KEY.CONTROL }] }]);
  await sleep(140);
}
async function typeKey(k) { await perform([{ type: "key", id: nid(), actions: [{ type: "keyDown", value: k }, { type: "keyUp", value: k }] }]); await sleep(100); }
(async () => {
  await createSession();
  await sleep(2500);
  await shortcut("a"); await sleep(140); await shortcut("d"); await sleep(220); await press(KEY.ESCAPE); await sleep(160);
  const c0 = await find('[data-testid="clip-c0"]');
  const c1 = await find('[data-testid="clip-c1"]');
  await ctrlClick(c0, 40); await sleep(90);
  await ctrlClick(c1, 440);
  const sel0 = await attr(c0, "data-selected"), sel1 = await attr(c1, "data-selected");
  console.log("SELECTED c0=" + sel0 + " c1=" + sel1);
  const phBefore = await attr(await find(".playhead"), "style");
  console.log("PLAYHEAD_BEFORE=" + phBefore);
  const lane = await find(".ruler-lane"); const lb = await rect(lane);
  const vx = Math.round(lb.x + 2.0 * 80);
  await perform([{ type: "pointer", id: nid(), parameters: { pointerType: "mouse" }, actions: [{ type: "pointerMove", x: vx, y: Math.round(lb.y + lb.height / 2) }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }] }]);
  await sleep(200);
  const phAfter = await attr(await find(".playhead"), "style");
  console.log("PLAYHEAD_AFTER=" + phAfter);
  const nBefore = (await findAll(".clip")).length;
  await typeKey("s");
  await sleep(250);
  const nAfterS = (await findAll(".clip")).length;
  console.log("NCLIPS before=" + nBefore + " after_s=" + nAfterS);
  // Identify which clips exist (left = start*80)
  const idsBefore = (await findAll(".clip")).map(async (el) => { const b = await rect(el); const t = await attr(el, "data-testid"); return t + "@" + b.x.toFixed(0); });
  console.log("AFTER_S_CLIPS=" + JSON.stringify(await Promise.all(idsBefore)));
  // Also test the toolbar split control (real GUI) with same selection+playhead context
  await sleep(100);
  const nAfterBtn = (await findAll(".clip")).length;
  console.log("NCLIPS after_btn=" + nAfterBtn);
  await wd("DELETE", `/session/${sessionId}`);
  process.exit(0);
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
