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
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed ${res.status}`);
  return payload.value;
}

async function createSession() {
  const shims = "C:/Users/chara/scoop/shims";
  const envPath = (process.env.PATH || "").includes(shims) ? process.env.PATH : `${shims};${process.env.PATH || ""}`;
  const value = await wd("POST", "/session", {
    capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, env: { PATH: envPath } } } },
  });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}
async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function maybeFind(css) {
  try { return await find(css); } catch { return null; }
}
async function waitFor(css, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const id = await maybeFind(css);
    if (id) return id;
    await sleep(80);
  }
  throw new Error(`${css} not found`);
}
async function waitAbsent(css, timeout = 4000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (!(await maybeFind(css))) return;
    await sleep(100);
  }
  throw new Error(`${css} still present after ${timeout}ms`);
}
async function text(id) {
  return wd("GET", `/session/${sessionId}/element/${id}/text`);
}
async function rect(id) {
  return wd("GET", `/session/${sessionId}/element/${id}/rect`);
}
async function click(id) {
  const b = await rect(id);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{
    type: "pointer", id: "mouse", parameters: { pointerType: "mouse" },
    actions: [{ type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + b.width / 2), y: Math.round(b.y + b.height / 2) }, { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 }],
  }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(120);
}
async function typeInto(id, value) {
  await wd("POST", `/session/${sessionId}/element/${id}/value`, { text: value, value: [...value] });
  await sleep(80);
}
function pass(name) { console.log(`${name}=PASS`); }

async function main() {
  await createSession();
  gate = "HARNESS_SESSION_START";
  pass(gate);

  gate = "CAPTION_WORKSPACE_VISIBLE";
  await waitFor('[data-testid="caption-workspace"]');
  pass(gate);

  gate = "CAPTION_ADD";
  const input = await find('[data-testid="caption-text"]');
  await typeInto(input, "R2.4 caption proof");
  const addBtn = await find('[data-testid="caption-add"]');
  await wd("POST", `/session/${sessionId}/element/${addBtn}/click`, {});
  await sleep(120);
  const row = await waitFor('[data-testid="caption-row-cap-1"]');
  assert.match(await text(row), /R2\.4 caption proof/);
  pass(gate);
  gate = "CAPTION_PREVIEW_OVERLAY";
  const overlay = await waitFor('.caption-overlay');
  assert.equal((await text(overlay)).trim(), "R2.4 caption proof");
  pass(gate);
  gate = "CAPTION_DELETE";
  const deleteBtn = await find('[data-testid="caption-delete-cap-1"]');
  await wd("POST", `/session/${sessionId}/element/${deleteBtn}/click`, {});
  await sleep(150);
  await waitAbsent('[data-testid="caption-row-cap-1"]');
  pass(gate);

  gate = "CAPTION_UNDO_RESTORE";
  const undo = await find('button[title="Ctrl+Z"]');
  await click(undo);
  await waitFor('[data-testid="caption-row-cap-1"]');
  const restored = await waitFor('.caption-overlay');
  assert.equal((await text(restored)).trim(), "R2.4 caption proof");
  pass(gate);

  gate = "REAL_GUI_RUNTIME";
  const title = await wd("GET", `/session/${sessionId}/title`);
  assert.ok(title.startsWith("HAIOS AI Video Studio"));
  pass(gate);
}

try {
  await main();
} catch (error) {
  console.error(`${gate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
