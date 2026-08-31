import assert from "node:assert/strict";
const DRIVER = "http://127.0.0.1:4444";
const APP = "C:/Workspace/super-creator-os/apps/desktop/src-tauri/target/release/haios-video-studio.exe";
const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
let sessionId = null;
let gate = "SESSION";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function wd(method, path, body) {
  const res = await fetch(`${DRIVER}${path}`, { method, headers: body === undefined ? undefined : { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload?.value?.message ?? `${method} ${path} failed ${res.status}`);
  return payload.value;
}
async function createSession() {
  const shims = "C:/Users/chara/scoop/shims";
  const envPath = (process.env.PATH || "").includes(shims) ? process.env.PATH : `${shims};${process.env.PATH || ""}`;
  const value = await wd("POST", "/session", { capabilities: { alwaysMatch: { browserName: "webview2", "tauri:options": { application: APP, env: { PATH: envPath } } } } });
  sessionId = value.sessionId;
  await wd("POST", `/session/${sessionId}/window/rect`, { width: 1440, height: 900 });
}
async function find(css) { return (await wd("POST", `/session/${sessionId}/element`, { using: "css selector", value: css }))[ELEMENT]; }
async function rect(id) { return wd("GET", `/session/${sessionId}/element/${id}/rect`); }
async function prop(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/property/${name}`); }
async function attr(id, name) { return wd("GET", `/session/${sessionId}/element/${id}/attribute/${name}`); }
async function pointerClick(css, xOffset, yOffset) {
  const el = await find(css); const b = await rect(el);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{ type: "pointer", id: "mouse", parameters: { pointerType: "mouse" }, actions: [
    { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + xOffset), y: Math.round(b.y + yOffset) },
    { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
  ] }] });
  await wd("DELETE", `/session/${sessionId}/actions`); await sleep(250);
}
async function setInput(css, value) {
  const script = `const el=document.querySelector(arguments[0]); if(!el) return null; const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; set.call(el,String(arguments[1])); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); return el.value;`;
  return wd("POST", `/session/${sessionId}/execute/sync`, { script, args: [css, value] });
}
function pass(name) { console.log(`${name}=PASS`); }
async function main() {
  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);
  await pointerClick('[data-testid="clip-c0"]', 30, 18);
  gate = "SPEED_CONTROL_VISIBLE";
  const speed = await find('[data-testid="clip-speed"]');
  assert.equal(Number(await prop(speed, "value")), 1); pass(gate);

  gate = "SPEED_COMMAND_COMMITTED";
  await setInput('[data-testid="clip-speed"]', 2); await sleep(300);
  const c0 = await find('[data-testid="clip-c0"]');
  assert.ok(Math.abs(Number(await attr(c0, "data-duration")) - 1) < 0.01); pass(gate);

  gate = "SPEED_PREVIEW_RATE";
  const ruler = await find(".ruler-lane"); const rb = await rect(ruler);
  await pointerClick(".ruler-lane", 0.5 * 80, rb.height / 2);
  const video = await find(".preview-video");
  assert.equal(Number(await prop(video, "playbackRate")), 2); pass(gate);

  gate = "REAL_GUI_RUNTIME";
  assert.ok((await wd("GET", `/session/${sessionId}/title`)).startsWith("HAIOS AI Video Studio")); pass(gate);
}
try { await main(); }
catch (error) { console.error(`${gate}=FAIL`); console.error(error instanceof Error ? error.stack : String(error)); process.exitCode = 1; }
finally { if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined); }
