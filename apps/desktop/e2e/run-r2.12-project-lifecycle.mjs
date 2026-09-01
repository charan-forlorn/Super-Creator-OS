import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ARTIFACT_DIR = "C:/Workspace/super-creator-os/apps/desktop/e2e/artifacts";
const PROJECT_PATH = path.join(ARTIFACT_DIR, "r2.12-project-lifecycle.haip.json").replaceAll("\\", "/");
let sessionId = null;
let gate = "SESSION";

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
    const command = arguments[0];
    const args = arguments[1];
    const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
    if (typeof invoke !== 'function') { done({ ok: false, error: 'TAURI_INVOKE_UNAVAILABLE' }); return; }
    invoke(command, args).then((value) => done({ ok: true, value })).catch((error) => done({ ok: false, error: String(error) }));
  `;
  const result = await wd("POST", `/session/${sessionId}/execute/async`, { script, args: [command, args] });
  if (!result?.ok) throw new Error(result?.error ?? `${command} failed`);
  return result.value;
}

function pass(name) { console.log(`${name}=PASS`); }
const baseProject = {
  schemaVersion: 2,
  id: "r2-12-e2e",
  name: "Lifecycle Old",
  createdAt: "2026-09-01T00:00:00.000Z",
  updatedAt: "2026-09-01T00:00:00.000Z",
  assets: [],
  tracks: [],
  durationSec: 0,
  aspectRatio: "1920x1080",
};

async function main() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  for (const candidate of [PROJECT_PATH, `${PROJECT_PATH}.bak`, `${PROJECT_PATH}.tmp`]) {
    fs.rmSync(candidate, { force: true });
  }

  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);

  gate = "PROJECT_LIFECYCLE_CONTROLS_VISIBLE";
  const controls = await execSync(`return Array.from(document.querySelectorAll('.top-bar button')).map((x) => x.textContent.trim());`);
  assert.ok(["New", "Open", "Save", "Save As", "Export"].every((label) => controls.includes(label)));
  assert.equal(await execSync(`return Boolean(document.querySelector('.recent-projects'));`), true);
  pass(gate);

  const oldJson = JSON.stringify(baseProject, null, 2);
  const newProject = { ...baseProject, name: "Lifecycle New", updatedAt: "2026-09-01T00:01:00.000Z" };
  const newJson = JSON.stringify(newProject, null, 2);
  gate = "PROJECT_SAVE_TAURI_COMMAND";
  await invoke("project_save", { path: PROJECT_PATH, projectJson: oldJson });
  assert.equal(fs.existsSync(PROJECT_PATH), true);
  await invoke("project_save", { path: PROJECT_PATH, projectJson: newJson });
  assert.equal(JSON.parse(fs.readFileSync(PROJECT_PATH, "utf8")).name, "Lifecycle New");
  pass(gate);

  gate = "PROJECT_BACKUP_ROTATION";
  const backupPath = `${PROJECT_PATH}.bak`;
  assert.equal(fs.existsSync(backupPath), true);
  assert.equal(JSON.parse(fs.readFileSync(backupPath, "utf8")).name, "Lifecycle Old");
  pass(gate);

  gate = "PROJECT_OPEN_ROUNDTRIP";
  const reopened = await invoke("project_open", { path: PROJECT_PATH });
  assert.deepEqual(JSON.parse(reopened), newProject);
  pass(gate);

  gate = "PROJECT_AUTOSAVE_RUNTIME";
  await invoke("project_autosave", {
    projectId: newProject.id,
    projectJson: newJson,
    projectPath: PROJECT_PATH,
  });
  const latest = await invoke("project_latest_autosave", {});
  assert.equal(latest.projectId, newProject.id);
  assert.equal(latest.projectPath, PROJECT_PATH);
  assert.deepEqual(JSON.parse(latest.projectJson), newProject);
  pass(gate);
  gate = "PROJECT_AUTOSAVE_CLEAR";
  assert.equal(await invoke("project_clear_autosave", { projectId: newProject.id }), true);
  const afterClear = await invoke("project_latest_autosave", {});
  assert.notEqual(afterClear?.projectId, newProject.id, "cleared project autosave must not remain latest");
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
  for (const candidate of [PROJECT_PATH, `${PROJECT_PATH}.bak`, `${PROJECT_PATH}.tmp`]) {
    fs.rmSync(candidate, { force: true });
  }
}
