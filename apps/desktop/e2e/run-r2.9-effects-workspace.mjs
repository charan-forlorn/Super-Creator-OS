import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "SESSION";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wd(method, path, body) {
  const res = await fetch(`${DRIVER}${path}`, { method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
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
async function find(css) { return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT]; }
async function rect(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function prop(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/property/${name}`); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function setNumber(css, value) {
  const id = await find(css);
  await wd("POST", `/session/${sessionId}/element/${id}/clear`, {});
  await wd("POST", `/session/${sessionId}/element/${id}/value`, { text: String(value), value: [...String(value)] });
  await sleep(220);
  assert.equal(Number(await prop(id, "value")), Number(value));
}
async function pointerClickClip(id) {
  const el = await find(`[data-testid="clip-${id}"]`);
  const b = await rect(el);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{ type: "pointer", id: "mouse",
    parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + 35), y: Math.round(b.y + b.height / 2) },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
    ] }] });
  await wd("DELETE", `/session/${sessionId}/actions`);
  await sleep(180);
}
function pass(name) { console.log(`${name}=PASS`); }
async function main() {
  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);
  await pointerClickClip("c0");
  gate = "EFFECTS_CONTROLS_VISIBLE";
  for (const id of ["effects-brightness", "effects-contrast", "effects-saturation"]) {
    assert.ok(await find(`[data-testid="${id}"]`));
  }
  pass(gate);
  const video = await find("video.preview-video");
  gate = "EFFECTS_DEFAULT_PREVIEW";
  let style = String(await attr(video, "style"));
  assert.match(style, /brightness\(1\)/);
  assert.match(style, /contrast\(1\)/);
  assert.match(style, /saturate\(1\)/);
  pass(gate);
  await setNumber('[data-testid="effects-brightness"]', 0.25);
  await setNumber('[data-testid="effects-contrast"]', 1.5);
  await setNumber('[data-testid="effects-saturation"]', 0.4);
  gate = "EFFECTS_PREVIEW_FIDELITY";
  style = String(await attr(video, "style"));
  assert.match(style, /brightness\(1\.25\)/);
  assert.match(style, /contrast\(1\.5\)/);
  assert.match(style, /saturate\(0\.4\)/);
  pass(gate);
  gate = "REAL_GUI_RUNTIME";
  assert.ok((await wd("GET", `/session/${sessionId}/title`)).startsWith("HAIOS AI Video Studio"));
  pass(gate);
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
