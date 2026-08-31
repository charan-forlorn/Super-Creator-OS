// R2.0 — pure-node verification tests for the Fixed WebView2 reproducible baseline.
//
// These assert the *real* on-disk + pinned state. They do NOT mock: they read the
// actual checksum manifest, locate the real extracted runtime directory, and
// compute the actual SHA-256 of msedgewebview2.exe, comparing it to the pin.
//
// Run with:  node scripts/webview2-bootstrap.test.mjs
// (also wired as `pnpm webview2:verify` via scripts/webview2-verify.mjs)

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = resolve(__dirname, "..");
const CHECKSUM_FILE = join(__dirname, "webview2-runtime.checksum.json");

function sha256OfFile(path) {
  const h = createHash("sha256");
  h.update(readFileSync(path));
  return h.digest("hex");
}

let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  ok  - ${name}`);
  } catch (e) {
    console.error(`  FAIL- ${name}`);
    console.error(`        ${e.message}`);
    process.exitCode = 1;
  }
}

console.log("R2.0 WebView2 reproducible-baseline verification");

const pin = JSON.parse(readFileSync(CHECKSUM_FILE, "utf8"));
const { version, arch, integrityTarget, officialSource, extractedDirName } = pin;

check("checksum manifest pins a fixed version + architecture", () => {
  assert.match(version, /^\d+\.\d+\.\d+\.\d+$/, "version must be x.y.z.w");
  assert.equal(arch, "x64", "architecture must be x64 (the only supported Tauri target here)");
});

check("official source is the Microsoft msedgedl endpoint (no mirror)", () => {
  const u = new URL(officialSource);
  assert.equal(u.host, "msedgedl.blob.core.windows.net", "must be official Microsoft host");
  assert.ok(u.pathname.includes(version), "URL must contain the pinned version");
  assert.ok(u.pathname.endsWith(".cab"), "source artifact must be the .cab");
});

check("extractedDirName matches tauri.conf.json fixedRuntime path", () => {
  assert.equal(extractedDirName, `Microsoft.WebView2.FixedVersionRuntime.${version}.${arch}`);
});

const runtimeDir = join(SRC_ROOT, "src-tauri", extractedDirName);

check("runtime directory exists on disk", () => {
  assert.ok(existsSync(runtimeDir), `missing: ${runtimeDir}`);
});

check("runtime directory is not empty (no 250MB commit is expected — gitignored)", () => {
  const n = readdirSync(runtimeDir).length;
  assert.ok(n > 0, "runtime dir should contain extracted binaries");
});

const targetExe = join(runtimeDir, integrityTarget);

check("integrity target (msedgewebview2.exe) is present", () => {
  assert.ok(existsSync(targetExe), `missing: ${targetExe}`);
  assert.ok(statSync(targetExe).size > 1_000_000, "host binary should be multi-MB");
});

check("integrity target SHA-256 matches the pinned authorization", () => {
  const actual = sha256OfFile(targetExe).toLowerCase();
  const expected = String(pin.expectedExtractedSha256).toLowerCase();
  assert.equal(actual, expected, "runtime binary must match the sealed pin");
});

check("additional expected artifacts are present", () => {
  for (const a of pin.additionalExpectedArtifacts || []) {
    assert.ok(existsSync(join(runtimeDir, a)), `missing expected artifact: ${a}`);
  }
});

console.log(
  process.exitCode
    ? "\nRESULT: FAIL — R2.0 reproducible baseline NOT satisfied"
    : `\nRESULT: PASS — R2.0 reproducible baseline satisfied (${passed} checks)`,
);
process.exit(process.exitCode || 0);
