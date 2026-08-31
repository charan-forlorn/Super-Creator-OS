#!/usr/bin/env node
// R2.0 — deterministic Fixed WebView2 runtime verification.
//
// Verifies the *extracted* runtime that Tauri loads via 'fixedRuntime' bundle
// mode (see apps/desktop/src-tauri/tauri.conf.json). The runtime binary is
// intentionally NOT committed (gitignored). This script is the integrity gate
// for the R2.0 reproducible-baseline checkpoint:
//
//   WEBVIEW_FIXED_VERSION_PINNED=TRUE
//   WEBVIEW_BOOTSTRAP_REPRODUCIBLE=TRUE
//   NO_250MB_RUNTIME_COMMITTED=TRUE   (enforced by .gitignore)
//   BUILD_FROM_FRESH_RUNTIME_STATE=PASS
//
// The authoritative integrity target is the extracted `msedgewebview2.exe`
// SHA-256 pinned in scripts/webview2-runtime.checksum.json. Microsoft does not
// publish a checksum for the CAB, so we verify the real artifact the host loads,
// not the transport file. This is fail-closed: any drift fails the gate.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = resolve(__dirname, "..");
const CHECKSUM_FILE = join(__dirname, "webview2-runtime.checksum.json");

function fail(msg) {
  console.error(`[webview2-verify] FAIL: ${msg}`);
  process.exitCode = 1;
  return false;
}

function sha256OfFile(path) {
  const h = createHash("sha256");
  const buf = readFileSync(path);
  h.update(buf);
  return h.digest("hex");
}

function main() {
  if (!existsSync(CHECKSUM_FILE)) {
    return fail(`checksum manifest missing: ${CHECKSUM_FILE}`);
  }
  const pin = JSON.parse(readFileSync(CHECKSUM_FILE, "utf8"));
  const version = pin.version;
  const arch = pin.arch;
  const expected = String(pin.expectedExtractedSha256).toLowerCase();
  const integrityTarget = pin.integrityTarget;
  const runtimeDir = join(
    SRC_ROOT,
    "src-tauri",
    `Microsoft.WebView2.FixedVersionRuntime.${version}.${arch}`,
  );
  const targetExe = join(runtimeDir, integrityTarget);

  console.log(`[webview2-verify] pin: ${pin.product} ${version} ${arch}`);
  console.log(`[webview2-verify] official source: ${pin.officialSource}`);
  console.log(`[webview2-verify] runtime dir: ${runtimeDir}`);

  if (!existsSync(runtimeDir)) {
    return fail(
      `runtime directory not found: ${runtimeDir}\n` +
        `  Run: node scripts/webview2-bootstrap.mjs  (requires network egress to ${new URL(pin.officialSource).host})`,
    );
  }

  let entries = [];
  try {
    entries = readdirSync(runtimeDir);
  } catch (e) {
    return fail(`cannot read runtime directory: ${e.message}`);
  }
  if (entries.length === 0) {
    return fail(`runtime directory is empty: ${runtimeDir}`);
  }

  // Optional artifact presence checks (non-fatal but reported).
  const extra = pin.additionalExpectedArtifacts || [];
  for (const a of extra) {
    const p = join(runtimeDir, a);
    if (!existsSync(p)) {
      console.warn(`[webview2-verify] WARN: expected artifact missing: ${a}`);
    }
  }

  if (!existsSync(targetExe)) {
    return fail(`integrity target missing: ${targetExe}`);
  }

  const actual = sha256OfFile(targetExe).toLowerCase();
  console.log(`[webview2-verify] ${integrityTarget} SHA-256:`);
  console.log(`[webview2-verify]   expected: ${expected}`);
  console.log(`[webview2-verify]   actual:   ${actual}`);

  if (actual !== expected) {
    return fail(
      `integrity MISMATCH on ${integrityTarget}. The extracted runtime does not match the pinned authorization. ` +
        `Refusing to bootstrap from an unverified WebView2 runtime.`,
    );
  }

  const size = statSync(targetExe).size;
  console.log(
    `[webview2-verify] PASS — runtime ${version} ${arch} verified (SHA-256 match, ${(size / 1e6).toFixed(1)} MB).`,
  );
  console.log(
    JSON.stringify({
      status: "PASS",
      version,
      arch,
      integrityTarget,
      sha256: actual,
      runtimeDir,
      artifacts: entries.length,
    }),
  );
  process.exitCode = 0;
}

main();
