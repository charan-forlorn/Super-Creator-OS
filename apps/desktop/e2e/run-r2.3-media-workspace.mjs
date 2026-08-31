#!/usr/bin/env node
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let sessionId = null;
let currentGate = "HARNESS_SESSION_START";

async function wd(method, endpoint, body) {
  const response = await fetch(`${DRIVER}${endpoint}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.value?.message ?? `${method} ${endpoint} failed ${response.status}`);
  return payload.value;
}

async function createSession() {
  const shims = "C:/Users/chara/scoop/shims";
  const existing = process.env.PATH || "";
  const injected = existing.includes(shims) ? existing : `${shims};${existing}`;
  const value = await wd("POST", "/session", {
    capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [], env: { PATH: injected } } } },
  });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}

async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function maybeFind(css) { try { return await find(css); } catch { return null; } }
async function waitFor(css, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`).catch(() => false)) return id;
    await sleep(100);
  }
  throw new Error(`${css} was not visibly rendered`);
}
async function text(id) { return wd("GET", `/session/${sessionId}/element/${id}/text`); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function prop(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/property/${name}`); }
async function rect(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function actions(body) {
  await wd("POST", `/session/${sessionId}/actions`, { actions: body });
  await wd("DELETE", `/session/${sessionId}/actions`);
}
async function click(id) {
  const b = await rect(id);
  const x = Math.round(b.x + Math.min(40, b.width / 2));
  const y = Math.round(b.y + b.height / 2);
  await actions([{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x, y },
    { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
  ] }]);
  await sleep(120);
}
async function waitText(css, expected, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id) {
      const value = (await text(id)).trim().toLowerCase();
      if (value === expected.toLowerCase()) return id;
    }
    await sleep(150);
  }
  throw new Error(`${css} never became ${expected}`);
}
function pass(name) { console.log(`${name}=PASS`); }

async function main() {
  const t0 = Date.now();
  await createSession();
  pass("HARNESS_SESSION_START");

  currentGate = "BACKGROUND_ANALYSIS_NON_BLOCKING";
  const c0 = await waitFor('[data-testid="clip-c0"]', 5000);
  await click(c0);
  assert.equal(await attr(c0, "data-selected"), "true", "timeline must remain interactive while media analysis runs");
  assert.ok(Date.now() - t0 < 5000, "first GUI interaction must not wait for derived-media analysis");
  pass(currentGate);

  currentGate = "MEDIA_BIN";
  await waitFor('[data-testid="media-bin"]');
  for (const id of ["asset-fixture", "asset-prores", "asset-missing"]) {
    await waitFor(`[data-testid="media-item-${id}"]`);
  }
  pass(currentGate);

  currentGate = "THUMBNAILS";
  const thumb = await waitFor('[data-testid="thumbnail-asset-fixture"]', 30000);
  const thumbWidth = Number(await prop(thumb, "naturalWidth").catch(() => 0));
  assert.ok(thumbWidth > 0, `thumbnail must decode in WebView2 (naturalWidth=${thumbWidth})`);
  pass(currentGate);

  currentGate = "METADATA";
  await waitText('[data-testid="analysis-status-asset-fixture"]', "ready", 30000);
  const item = await find('[data-testid="media-item-asset-fixture"]');
  const itemText = await text(item);
  assert.match(itemText, /320×240/);
  assert.match(itemText, /25\.00 fps/);
  assert.match(itemText, /V h264/);
  assert.match(itemText, /A aac/);
  assert.match(itemText, /Audio yes/);
  pass(currentGate);

  currentGate = "WAVEFORM";
  const wave = await waitFor('[data-testid="waveform-asset-fixture"]', 30000);
  const waveWidth = Number(await prop(wave, "naturalWidth").catch(() => 0));
  assert.ok(waveWidth > 0, `waveform PNG must decode in WebView2 (naturalWidth=${waveWidth})`);
  pass(currentGate);

  currentGate = "MISSING_MEDIA_DETECTION";
  await waitText('[data-testid="analysis-status-asset-missing"]', "missing", 15000);
  const missingItem = await find('[data-testid="media-item-asset-missing"]');
  assert.ok((await attr(missingItem, "class")).includes("missing"));
  pass(currentGate);

  currentGate = "MEDIA_RELINK_UI";
  const relink = await waitFor('[data-testid="relink-asset-missing"]');
  assert.equal((await text(relink)).trim(), "Relink");
  pass(currentGate);

  currentGate = "REAL_GUI_RUNTIME";
  const title = await wd("GET", `/session/${sessionId}/title`);
  assert.ok(title.startsWith("HAIOS AI Video Studio"));
  pass(currentGate);
}

try {
  await main();
} catch (error) {
  console.error(`${currentGate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
