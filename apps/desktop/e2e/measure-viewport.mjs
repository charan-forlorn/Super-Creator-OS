#!/usr/bin/env node
/**
 * R2.1 PHASE 1 — READ-ONLY viewport / scroll-container root-cause measurement.
 * Uses only W3C-supported commands: window/rect, element/rect, element/property.
 * No JS execute, no scrolling, no clicking, no product mutation.
 */
import assert from "node:assert/strict";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";

let sessionId = null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function wd(method, path, body) {
  const response = await fetch(`${DRIVER}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.value?.message ?? `${method} ${path} failed: ${response.status}`;
    throw new Error(message);
  }
  return payload.value;
}
async function find(css) {
  return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT];
}
async function maybeFind(css) {
  try { return await find(css); } catch { return null; }
}
async function waitFor(css, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const id = await maybeFind(css);
    if (id && await wd("GET", `/session/${sessionId}/element/${id}/displayed`)) return id;
    await sleep(50);
  }
  throw new Error(`${css} not visibly rendered`);
}
async function rectOf(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function propOf(id, name) {
  try { return await wd("GET", `/session/${sessionId}/element/${id}/property/${name}`); }
  catch { return null; }
}

async function describe(css) {
  const id = await maybeFind(css);
  if (!id) return { selector: css, exists: false };
  const b = await rectOf(id);
  const overflowY = await propOf(id, "overflowY");
  const overflowX = await propOf(id, "overflowX");
  const scrollH = await propOf(id, "scrollHeight");
  const clientH = await propOf(id, "clientHeight");
  const scrollW = await propOf(id, "scrollWidth");
  const clientW = await propOf(id, "clientWidth");
  const scrollTop = await propOf(id, "scrollTop");
  const scrollLeft = await propOf(id, "scrollLeft");
  const tagName = await propOf(id, "tagName");
  const className = await propOf(id, "className");
  const canScrollY = (scrollH != null && clientH != null) && (scrollH - clientH > 1);
  const allowsScroll = ["auto", "scroll", "hidden"].includes(overflowY) || ["auto", "scroll", "hidden"].includes(overflowX);
  return {
    selector: css, exists: true, tag: tagName, cls: typeof className === "string" ? className : String(className),
    x: b.x, y: b.y, w: b.width, h: b.height,
    top: b.y, bottom: b.y + b.height, left: b.x, right: b.x + b.width,
    overflowY, overflowX, scrollH, clientH, scrollW, clientW, scrollTop, scrollLeft,
    canScrollY, allowsScroll,
  };
}

async function main() {
  const cap = await wd("POST", "/session", {
    capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, args: [] } } },
  });
  sessionId = cap.sessionId;
  console.log("SESSION_STARTED=" + sessionId);
  await waitFor('[data-testid="clip-c0"]');

  const win = await wd("GET", `/session/${sessionId}/window/rect`);
  console.log("WINDOW_RECT=" + JSON.stringify(win));

  const selectors = ["html", "body", "#root", ".app", ".editor", ".timeline", ".timeline-scroll", ".track-video", ".ruler", ".playhead", '[data-testid="clip-c0"]', '[data-testid="clip-c1"]', '[data-testid="clip-c2"]'];
  const out = {};
  for (const s of selectors) out[s] = await describe(s);
  console.log("MEASUREMENT=" + JSON.stringify(out, null, 2));
}

try {
  await main();
} catch (error) {
  console.error("MEASURE_FAIL");
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
