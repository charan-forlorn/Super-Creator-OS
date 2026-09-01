import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ROOT = "C:/Workspace/super-creator-os/apps/desktop";
const SAMPLE = `${ROOT}/e2e/fixtures/sample.mp4`;
const ARTIFACT_DIR = `${ROOT}/e2e/artifacts`;
const OUTPUT = `${ARTIFACT_DIR}/r2.13-render.mp4`;
const CANCEL_OUTPUT = `${ARTIFACT_DIR}/r2.13-cancel.mp4`;
let sessionId = null;
let gate = "SESSION";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function wd(method, endpoint, body) {
  const res = await fetch(`${DRIVER}${endpoint}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${endpoint} failed ${res.status}`);
  return payload.value;
}

async function createSession() {
  const shims = "C:/Users/chara/scoop/shims";
  const envPath = (process.env.PATH || "").includes(shims)
    ? process.env.PATH
    : `${shims};${process.env.PATH || ""}`;
  const value = await wd("POST", "/session", {
    capabilities: {
      alwaysMatch: {
        browserName: "webview2",
        "tauri:options": { application: APP, env: { PATH: envPath } },
      },
    },
  });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}

async function execSync(script, args = []) {
  return wd("POST", `/session/${sessionId}/execute/sync`, { script, args });
}

async function invoke(command, args = {}) {
  const script = `
    const done = arguments[arguments.length - 1];
    const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
    if (typeof invoke !== 'function') { done({ ok: false, error: 'TAURI_INVOKE_UNAVAILABLE' }); return; }
    invoke(arguments[0], arguments[1]).then((value) => done({ ok: true, value })).catch((error) => done({ ok: false, error: String(error) }));
  `;
  const result = await wd("POST", `/session/${sessionId}/execute/async`, { script, args: [command, args] });
  if (!result?.ok) throw new Error(result?.error ?? `${command} failed`);
  return result.value;
}

async function waitForStatus(pattern, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const text = await execSync(`return document.querySelector('.status')?.textContent || '';`);
    if (pattern.test(text)) return text;
    await sleep(80);
  }
  throw new Error(`status timeout: ${pattern}`);
}

function pass(name) { console.log(`${name}=PASS`); }
function projectWithClips(id, count, clipDuration) {
  const clips = Array.from({ length: count }, (_, i) => ({
    id: `${id}-clip-${i}`, assetId: `${id}-asset`, inPoint: 0,
    duration: clipDuration, start: i * clipDuration, trackId: `${id}-video`,
    playbackRate: 1, transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    effects: { brightness: 0, contrast: 1, saturation: 1 },
    transitionIn: null, audio: { gainDb: 0, muted: false },
  }));
  return {
    schemaVersion: 1, id, name: `R2.13 ${id}`,
    createdAt: "2026-09-01T00:00:00.000Z",
    updatedAt: "2026-09-01T00:00:00.000Z",
    assets: [{
      id: `${id}-asset`, name: "sample.mp4", sourcePath: SAMPLE,
      kind: "video", durationSec: 12, width: 320, height: 240,
      fps: 30, hasAudio: true, createdAt: "2026-09-01T00:00:00.000Z",
    }],
    tracks: [{ id: `${id}-video`, kind: "video", clips, captions: [] }],
    durationSec: count * clipDuration,
    aspectRatio: "1920x1080",
  };
}

async function armStatusHistory() {
  return execSync(`
    const node = document.querySelector('.status');
    if (!node) return false;
    window.__r213Observer?.disconnect?.();
    window.__r213StatusHistory = [node.textContent || ''];
    window.__r213Observer = new MutationObserver(() => {
      window.__r213StatusHistory.push(node.textContent || '');
    });
    window.__r213Observer.observe(node, { childList: true, subtree: true, characterData: true });
    return true;
  `);
}

async function statusHistory() {
  return execSync(`return window.__r213StatusHistory || [];`);
}

async function armRawRenderEvents() {
  const script = `
    const done = arguments[arguments.length - 1];
    window.__r213RawEvents = [];
    const invoke = window.__TAURI_INTERNALS__?.invoke;
    const transform = window.__TAURI_INTERNALS__?.transformCallback;
    if (typeof invoke !== 'function' || typeof transform !== 'function') { done(false); return; }
    const handler = transform((event) => window.__r213RawEvents.push(event.payload), false);
    invoke('plugin:event|listen', { event: 'render-progress', target: { kind: 'Any' }, handler })
      .then((eventId) => { window.__r213RawEventId = eventId; done(true); })
      .catch(() => done(false));
  `;
  return wd("POST", `/session/${sessionId}/execute/async`, { script, args: [] });
}

async function rawRenderEvents() {
  return execSync(`return window.__r213RawEvents || [];`);
}

function assertSequence(history, labels) {
  let cursor = -1;
  for (const label of labels) {
    cursor = history.findIndex((text, index) => index > cursor && text.includes(label));
    assert.ok(cursor >= 0, `missing ordered status ${label}: ${JSON.stringify(history)}`);
  }
}

function cleanupRenderArtifacts(output) {
  fs.rmSync(output, { force: true });
  fs.rmSync(`${output}.haios-prev`, { force: true });
  const stem = path.basename(output, path.extname(output));
  for (const name of fs.readdirSync(ARTIFACT_DIR)) {
    if (name.startsWith(`.${stem}.`) && name.endsWith(".rendering.mp4")) {
      fs.rmSync(path.join(ARTIFACT_DIR, name), { force: true });
    }
  }
}

async function main() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  cleanupRenderArtifacts(OUTPUT);
  cleanupRenderArtifacts(CANCEL_OUTPUT);
  fs.writeFileSync(OUTPUT, "previous-output");
  fs.writeFileSync(CANCEL_OUTPUT, "previous-cancel-output");

  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);
  assert.equal(await armStatusHistory(), true);
  assert.equal(await armRawRenderEvents(), true);

  const project = projectWithClips("render", 2, 2);
  const jobId = await invoke("hvs_render", {
    projectJson: JSON.stringify(project), outputPath: OUTPUT,
    resolution: "1920x1080",
  });
  await waitForStatus(/Exported & verified:/, 30000);

  gate = "RENDER_EVENT_SEQUENCE";
  const rawEvents = (await rawRenderEvents()).filter((event) => event.jobId === jobId);
  assertSequence(rawEvents.map((event) => event.status), ["ANALYZING", "PREPARING", "RENDERING", "VERIFYING", "COMPLETED"]);
  const history = await statusHistory();
  assert.ok(history.some((text) => text.includes("Verifying")));
  assert.ok(history.some((text) => text.includes("Exported & verified")));
  pass(gate);

  gate = "BACKEND_VERIFY_BEFORE_COMPLETED";
  const verification = await invoke("verify_render", { outputPath: OUTPUT, resolution: "1920x1080" });
  assert.equal(verification.ok, true, verification.error || "verification failed");
  assert.ok(fs.statSync(OUTPUT).size > "previous-output".length);
  pass(gate);

  gate = "TEMP_FINALIZATION_CLEAN";
  assert.equal(fs.existsSync(`${OUTPUT}.haios-prev`), false);
  assert.equal(fs.readdirSync(ARTIFACT_DIR).some((name) => name.includes(jobId) && name.endsWith(".rendering.mp4")), false);
  pass(gate);

  gate = "TARGET_SWAP_AFTER_VERIFY";
  assert.notEqual(fs.readFileSync(OUTPUT, "utf8", { flag: "r" }).slice(0, 15), "previous-output");
  pass(gate);

  await armStatusHistory();
  await execSync(`window.__r213RawEvents = []; return true;`);
  const cancelProject = projectWithClips("cancel", 30, 2);
  const cancelJob = await invoke("hvs_render", {
    projectJson: JSON.stringify(cancelProject), outputPath: CANCEL_OUTPUT,
    resolution: "1920x1080",
  });
  await waitForStatus(/Rendering/, 20000);
  assert.equal(await invoke("cancel_render", { jobId: cancelJob }), true);
  await waitForStatus(/Export cancelled/, 20000);

  gate = "IN_FLIGHT_CANCEL";
  const cancelRaw = (await rawRenderEvents()).filter((event) => event.jobId === cancelJob);
  assertSequence(cancelRaw.map((event) => event.status), ["ANALYZING", "PREPARING", "RENDERING", "CANCELLED"]);
  const cancelHistory = await statusHistory();
  assert.ok(cancelHistory.some((text) => text.includes("Export cancelled")));
  pass(gate);

  gate = "CANCEL_PRESERVES_EXISTING_OUTPUT";
  assert.equal(fs.readFileSync(CANCEL_OUTPUT, "utf8"), "previous-cancel-output");
  assert.equal(fs.readdirSync(ARTIFACT_DIR).some((name) => name.includes(cancelJob) && name.endsWith(".rendering.mp4")), false);
  pass(gate);

  gate = "TERMINAL_JOB_REGISTRY_CLEANUP";
  let secondCancelError = "";
  try {
    await invoke("cancel_render", { jobId: cancelJob });
  } catch (error) {
    secondCancelError = String(error);
  }
  assert.match(secondCancelError, /unknown job id/i);
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
  cleanupRenderArtifacts(OUTPUT);
  cleanupRenderArtifacts(CANCEL_OUTPUT);
}
