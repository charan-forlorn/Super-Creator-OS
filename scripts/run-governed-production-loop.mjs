import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..");
const bindingPath = process.env.SCOS_QUALIFICATION_BINDING
  ? resolve(process.env.SCOS_QUALIFICATION_BINDING)
  : join(
      repoRoot,
      "evidence",
      "qualification-bindings",
      "HAIOS_AI_GENERATION_20260918.json",
    );
const evidenceDir = join(repoRoot, "evidence", "production-loop");
const aiProviders = await import(
  pathToFileURL(
    join(repoRoot, "packages", "ai-providers", "dist", "governedProductionLoop.js"),
  ).href,
);

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function gate(reason, details) {
  const observedAt = new Date().toISOString();
  const payload = {
    schema_version: "SCOS_PRODUCTION_LOOP_GATE_R1",
    observed_at: observedAt,
    status: "OPEN",
    gate: reason,
    details,
  };
  const path = join(
    evidenceDir,
    "GATE_" + observedAt.replace(/[:.]/g, "-") + ".json",
  );
  await writeFile(path, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.error(JSON.stringify(payload, null, 2));
  process.exitCode = 2;
}

const binding = JSON.parse(await readFile(bindingPath, "utf8"));
const sourceRepo = binding.source_repo;
const sourceCommit = execFileSync(
  "git",
  ["-C", sourceRepo, "rev-parse", "HEAD"],
  { encoding: "utf8" },
).trim();
if (sourceCommit !== binding.source_commit) {
  await gate("OPEN_STALE_QUALIFICATION", {
    reason: "HAIOS source commit drifted from qualification binding",
    expected: binding.source_commit,
    observed: sourceCommit,
  });
  process.exit();
}

const sourceBytes = await readFile(join(sourceRepo, binding.source_path));
const sourceHash = sha256(sourceBytes);
if (sourceHash.toLowerCase() !== String(binding.source_sha256).toLowerCase()) {
  await gate("OPEN_STALE_QUALIFICATION", {
    reason: "qualification source bytes changed",
    expected: binding.source_sha256,
    observed: sourceHash,
    sourcePath: binding.source_path,
  });
  process.exit();
}

const result = await aiProviders.runGovernedProductionLoop({
  instruction:
    process.env.SCOS_INSTRUCTION ??
    "Change the project aspect ratio to vertical 1080x1920 and return the minimal valid edit plan.",
  context: {
    projectSummary: "Governed local production-loop qualification run.",
  },
  baseUrl: process.env.SCOS_OLLAMA_URL ?? "http://127.0.0.1:11434",
  evidenceDir,
  qualification: {
    sourceRepo: binding.source_repo,
    sourceCommit: binding.source_commit,
    sourcePath: binding.source_path,
    sourceSha256: binding.source_sha256,
    models: binding.models,
  },
  modelOverride: process.env.SCOS_OLLAMA_MODEL || undefined,
});

console.log(
  JSON.stringify(
    {
      status: result.status,
      loopRunId: result.loopRunId,
      routeDecisionId: result.routeDecisionId,
      selectedModel: result.selectedModel,
      evidencePath: result.evidencePath,
      evidenceSha256: result.evidenceSha256,
      telemetry: result.telemetry,
      error: result.error,
    },
    null,
    2,
  ),
);

if (result.status !== "COMPLETED") {
  process.exitCode = 3;
}
