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
async function click(id) { await wd("POST", `/session/${sessionId}/element/${id}/click`, {}); await sleep(220); }
async function pointerClick(css, xOffset, yOffset) {
  const el = await find(css); const b = await rect(el);
  await wd("POST", `/session/${sessionId}/actions`, { actions: [{ type: "pointer", id: "mouse",
    parameters: { pointerType: "mouse" }, actions: [
      { type: "pointerMove", duration: 0, origin: "viewport", x: Math.round(b.x + xOffset), y: Math.round(b.y + yOffset) },
      { type: "pointerDown", button: 0 }, { type: "pointerUp", button: 0 },
    ] }] });
  await wd("DELETE", `/session/${sessionId}/actions`); await sleep(250);
}
async function pointerClickClip(id) {
  const el = await find(`[data-testid="clip-${id}"]`); const b = await rect(el);
  await pointerClick(`[data-testid="clip-${id}"]`, Math.min(35, b.width / 2), b.height / 2);
}
function opacityFromStyle(style) {
  const m = String(style).match(/opacity:\s*([0-9.]+)/); return m ? Number(m[1]) : NaN;
}
function pass(name) { console.log(`${name}=PASS`); }
async function main() {
  await createSession();
  gate = "HARNESS_SESSION_START"; pass(gate);
  await pointerClickClip("c1");
  gate = "TRANSITION_CONTROLS_VISIBLE";
  const apply = await find('[data-testid="transition-crossfade"]');
  assert.ok(apply); assert.ok(await find('[data-testid="transition-duration"]')); pass(gate);
  await click(apply);
  gate = "TRANSITION_OVERLAP_COMMITTED";
  const c1 = await find('[data-testid="clip-c1"]');
  assert.ok(Math.abs(Number(await attr(c1, "data-start")) - 1.5) < 0.01); pass(gate);

  gate = "TRANSITION_PREVIEW_DUAL_LAYER";
  const ruler = await find(".ruler-lane"); const rb = await rect(ruler);
  await pointerClick(".ruler-lane", 1.75 * 80, rb.height / 2);
  const outgoing = await find('[data-preview-visual="c0"]');
  const incoming = await find('[data-preview-visual="c1"]');
  assert.ok(outgoing && incoming); pass(gate);

  gate = "TRANSITION_PREVIEW_FIDELITY";
  const inOpacity = opacityFromStyle(await attr(incoming, "style"));
  const outOpacity = opacityFromStyle(await attr(outgoing, "style"));
  assert.ok(inOpacity > 0.35 && inOpacity < 0.65, `incoming opacity=${inOpacity}`);
  assert.ok(outOpacity > 0.35 && outOpacity < 0.65, `outgoing opacity=${outOpacity}`);
  assert.equal(await prop(incoming, "muted"), true, "visual incoming video must stay muted");
  assert.equal(await prop(outgoing, "muted"), true, "visual outgoing video must stay muted");
  const inAudio = await find('audio[data-preview-audio="c1"]');
  const outAudio = await find('audio[data-preview-audio="c0"]');
  const inVolume = Number(await prop(inAudio, "volume"));
  const outVolume = Number(await prop(outAudio, "volume"));
  assert.ok(inVolume > 0.35 && inVolume < 0.65, `incoming audio volume=${inVolume}`);
  assert.ok(outVolume > 0.35 && outVolume < 0.65, `outgoing audio volume=${outVolume}`);
  pass(gate);

  gate = "REAL_GUI_RUNTIME";
  assert.ok((await wd("GET", `/session/${sessionId}/title`)).startsWith("HAIOS AI Video Studio"));
  pass(gate);
}
try { await main(); }
catch (error) {
  console.error(`${gate}=FAIL`);
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
} finally {
  if (sessionId) await wd("DELETE", `/session/${sessionId}`).catch(() => undefined);
}
