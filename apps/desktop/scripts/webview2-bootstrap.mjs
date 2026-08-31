#!/usr/bin/env node
// R2.0 — deterministic Fixed WebView2 runtime acquisition + verification.
//
// Idempotent bootstrap for the Microsoft WebView2 Fixed Version Runtime used by
// Tauri 'fixedRuntime' bundle mode (apps/desktop/src-tauri/tauri.conf.json).
//
// Behavior:
//   1. If the extracted runtime already exists AND its integrity target
//      (msedgewebview2.exe) SHA-256 matches the pin, exit PASS (no-op).
//   2. Otherwise download the official CAB from the pinned Microsoft source,
//      extract it with the platform extractor (expand.exe / cabextract),
//      and re-verify the integrity target.
//   3. Any network failure, extraction failure, or hash mismatch is FAIL-CLOSED:
//      the build bootstrap is refused rather than proceeding with an unverified
//      or missing runtime.
//
// The runtime binary is intentionally NOT committed (gitignored). This script
// is the reproducible acquisition mechanism for the R2.0 baseline.

import { createHash } from "node:crypto";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  rmSync,
  readdirSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = resolve(__dirname, "..");
const CHECKSUM_FILE = join(__dirname, "webview2-runtime.checksum.json");

function fail(msg) {
  console.error(`[webview2-bootstrap] FAIL: ${msg}`);
  process.exitCode = 1;
}
function info(msg) {
  console.log(`[webview2-bootstrap] ${msg}`);
}

function sha256OfFile(path) {
  const h = createHash("sha256");
  h.update(readFileSync(path));
  return h.digest("hex");
}

async function download(url, dest) {
  info(`downloading ${url}`);
  const res = await fetch(url, { redirect: "follow" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText} for ${url}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(dest, buf);
  info(`downloaded ${(buf.length / 1e6).toFixed(1)} MB -> ${dest}`);
}

function extractCab(cab, outDir) {
  mkdirSync(outDir, { recursive: true });
  try {
    execFileSync("expand.exe", ["-F:*", cab, outDir], { stdio: "inherit" });
    info(`extracted via expand.exe -> ${outDir}`);
  } catch {
    info("expand.exe unavailable; trying cabextract (POSIX fallback)...");
    try {
      execFileSync("cabextract", ["-d", outDir, cab], { stdio: "inherit" });
      info(`extracted via cabextract -> ${outDir}`);
    } catch (e) {
      throw new Error(
        `no CAB extractor available (expand.exe / cabextract). ${e.message}`,
      );
    }
  }
}

async function main() {
  if (!existsSync(CHECKSUM_FILE)) {
    return fail(`checksum manifest missing: ${CHECKSUM_FILE}`);
  }
  const pin = JSON.parse(readFileSync(CHECKSUM_FILE, "utf8"));
  const { version, arch, integrityTarget, officialSource, cabFileName } = pin;
  const expected = String(pin.expectedExtractedSha256).toLowerCase();
  const runtimeDir = join(
    SRC_ROOT,
    "src-tauri",
    `Microsoft.WebView2.FixedVersionRuntime.${version}.${arch}`,
  );
  const targetExe = join(runtimeDir, integrityTarget);

  if (existsSync(targetExe)) {
    const actual = sha256OfFile(targetExe).toLowerCase();
    if (actual === expected) {
      info(
        `runtime already present and verified (${version} ${arch}, SHA-256 match). No-op.`,
      );
      console.log(
        JSON.stringify({ status: "PASS", mode: "cached", version, arch }),
      );
      process.exitCode = 0;
      return;
    }
    info(
      `existing runtime integrity MISMATCH (expected ${expected}, got ${actual}). Re-acquiring.`,
    );
    rmSync(runtimeDir, { recursive: true, force: true });
  }

  const cabPath = join(__dirname, cabFileName);
  try {
    await download(officialSource, cabPath);
  } catch (e) {
    return fail(
      `download failed: ${e.message}\n` +
        `  The official Fixed Version Runtime must be acquired from:\n` +
        `    ${officialSource}\n` +
        `  No untrusted mirror is permitted (security policy). Re-run with network egress.`,
    );
  }

  try {
    extractCab(cabPath, runtimeDir);
  } catch (e) {
    return fail(`extraction failed: ${e.message}`);
  } finally {
    try {
      rmSync(cabPath, { force: true });
    } catch {
      /* best-effort */
    }
  }

  if (!existsSync(targetExe)) {
    return fail(`integrity target missing after extraction: ${targetExe}`);
  }
  const actual = sha256OfFile(targetExe).toLowerCase();
  if (actual !== expected) {
    return fail(
      `post-extraction integrity MISMATCH on ${integrityTarget} ` +
        `(expected ${expected}, got ${actual}). Refusing unverified runtime.`,
    );
  }

  const artifacts = readdirSync(runtimeDir).length;
  info(
    `PASS — runtime ${version} ${arch} acquired and verified (SHA-256 match, ${artifacts} artifacts).`,
  );
  console.log(
    JSON.stringify({ status: "PASS", mode: "acquired", version, arch, artifacts }),
  );
  process.exitCode = 0;
}

main().catch((e) => fail(e?.message || String(e)));
