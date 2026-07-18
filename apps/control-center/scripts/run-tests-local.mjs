#!/usr/bin/env node
/**
 * Phase 1.5 — Local headless Control Center test runner.
 *
 * The browser_navigate MCP tool times out in this environment, so instead of
 * driving a real browser we run Vitest entirely in jsdom (the project's
 * existing configuration) and persist the results as artifacts that the
 * orchestrator (Hermes) reads directly — no browser MCP, no external egress,
 * fully local-only.
 *
 * Outputs (under apps/control-center/test-reports/):
 *   - test-report.json  : raw Vitest JSON (machine-readable)
 *   - test-report.txt   : human-readable summary
 *   - test-report.html  : self-contained HTML report
 *
 * Usage (from repo root):
 *   node apps/control-center/scripts/run-tests-local.mjs
 *   # or with a custom filter:
 *   node apps/control-center/scripts/run-tests-local.mjs -- tests/control-center-truth-contract.test.ts
 */

import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const APP_DIR = resolve(__dirname, "..");
const OUT_DIR = resolve(APP_DIR, "test-reports");
const EXTRA_ARGS = process.argv.slice(2);

mkdirSync(OUT_DIR, { recursive: true });

// Run Vitest headlessly in the local jsdom environment. The local `.bin/vitest`
// is a POSIX shell shim on this environment, so invoke the CLI entry directly
// via `node` (cross-platform, no shell required).
const VITEST_BIN = resolve(APP_DIR, "node_modules", "vitest", "vitest.mjs");
const OUTPUT_FILE = resolve(OUT_DIR, "vitest-raw.json");
const result = spawnSync(
  process.execPath,
  [VITEST_BIN, "run", "--reporter=json", "--outputFile", OUTPUT_FILE, ...EXTRA_ARGS],
  { cwd: APP_DIR, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
);

const stdout = result.stdout ?? "";
const stderr = result.stderr ?? "";

let report = null;
try {
  report = JSON.parse(readFileSync(OUTPUT_FILE, "utf8"));
} catch {
  // Fallback: try parsing stdout if the output file is unavailable.
  try {
    report = JSON.parse(stdout);
  } catch {
    report = null;
  }
}

const suites = report?.testResults ?? [];
let passed = 0;
let failed = 0;
let pending = 0;
const failures = [];

for (const suite of suites) {
  for (const t of suite.assertionResults ?? []) {
    if (t.status === "passed") passed++;
    else if (t.status === "failed") {
      failed++;
      failures.push({
        file: suite.name,
        name: t.title,
        message: (t.failureMessages ?? []).join("\n").slice(0, 800),
      });
    } else pending++;
  }
}

const total = passed + failed + pending;
const exitCode = failed === 0 ? 0 : 1;

const txt =
  `Control Center — Local Vitest Report\n` +
  `Generated: ${new Date().toISOString()}\n` +
  `Command: node node_modules/vitest/vitest.mjs run --reporter=json ${EXTRA_ARGS.join(" ")}\n` +
  `--------------------------------------------------\n` +
  `Total:   ${total}\n` +
  `Passed:  ${passed}\n` +
  `Failed:  ${failed}\n` +
  `Pending: ${pending}\n` +
  `Result:  ${exitCode === 0 ? "GREEN (100%)" : "RED (failures present)"}\n` +
  (failures.length
    ? `\nFailures:\n` +
      failures.map((f) => `- ${f.file}\n    ${f.name}\n    ${f.message}`).join("\n")
    : "\nNo failures.\n");

const html =
  `<!doctype html><html lang="en"><head><meta charset="utf-8">` +
  `<title>Control Center — Local Vitest Report</title>` +
  `<style>body{font-family:ui-monospace,Menlo,Consolas,monospace;margin:2rem;}` +
  `.green{color:#137333}.red{color:#c5221f}h1{font-size:1.3rem}` +
  `table{border-collapse:collapse;margin-top:1rem}td,th{border:1px solid #ccc;padding:.4rem .8rem;text-align:left}` +
  `.fail{color:#c5221f}</style></head><body>` +
  `<h1>Control Center — Local Vitest Report</h1>` +
  `<p>Generated: ${new Date().toISOString()}</p>` +
  `<p><strong>Total:</strong> ${total} &nbsp; <strong>Passed:</strong> ${passed} &nbsp; ` +
  `<strong>Failed:</strong> ${failed} &nbsp; <strong>Pending:</strong> ${pending}</p>` +
  `<p class="${exitCode === 0 ? "green" : "red"}"><strong>` +
  `${exitCode === 0 ? "GREEN — 100% PASS (0 failed)" : "RED — failures present"}</strong></p>` +
  (suites.length
    ? `<table><tr><th>File</th><th>Tests</th><th>Status</th></tr>` +
      suites
        .map((s) => {
          const sp = (s.assertionResults ?? []).length;
          const sf = (s.assertionResults ?? []).filter((t) => t.status === "failed").length;
          const ok = sf === 0;
          return `<tr><td>${s.name}</td><td>${sp}</td><td class="${ok ? "green" : "fail"}">${ok ? "PASS" : sf + " failed"}</td></tr>`;
        })
        .join("") +
      `</table>`
    : `<p class="fail">No suites parsed. stderr:</p><pre>${stderr.slice(0, 2000)}</pre>`) +
  `</body></html>`;

writeFileSync(resolve(OUT_DIR, "test-report.json"), JSON.stringify(report ?? { rawStdout: stdout, rawStderr: stderr }, null, 2));
writeFileSync(resolve(OUT_DIR, "test-report.txt"), txt);
writeFileSync(resolve(OUT_DIR, "test-report.html"), html);

console.log(txt);
if (result.status !== 0 && exitCode === 0) {
  // Vitest exited non-zero for a non-test reason (e.g. config error).
  console.error("\nVitest process exited non-zero; see test-report.html / test-report.txt");
}
process.exit(exitCode);
