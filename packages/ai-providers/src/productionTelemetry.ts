import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";

export interface ProductionExecutionTelemetry {
  readonly schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1";
  readonly loopRunId: string;
  readonly routeDecisionId: string;
  readonly observedAt: string;
  readonly startedAt: string;
  readonly completedAt: string;
  readonly durationMs: number;
  readonly capabilityId: string;
  readonly providerId: string;
  readonly modelId: string;
  readonly modelVersion?: string;
  readonly status: "COMPLETED" | "FAILED";
  readonly generationStatus: "COMPLETED" | "FAILED";
  readonly executionStatus: "NOT_RUN" | "COMPLETED" | "FAILED";
  readonly executedCommandTypes?: readonly string[];
  readonly projectBeforeSha256?: string;
  readonly projectAfterSha256?: string;
  readonly executionDurationMs?: number;
  readonly responseBytes?: number;
  readonly responseSha256?: string;
  /** Hash of the generation/routing contract that produced this observation. */
  readonly contractRevision: string;
  readonly requestSha256: string;
  readonly fallbackUsed: false;
  readonly error?: string;
  readonly evidenceRefs: readonly string[];
}

export interface ProductionEvidence {
  readonly schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1";
  readonly loopRunId: string;
  readonly routeDecisionId: string;
  readonly observedAt: string;
  readonly routeDecision: unknown;
  readonly qualification: {
    readonly sourceRepo: string;
    readonly sourceCommit: string;
    readonly sourcePath: string;
    readonly sourceSha256: string;
    readonly modelDigest: string;
  };
  readonly telemetry: ProductionExecutionTelemetry | null;
  readonly verification: {
    readonly status: "PASS" | "FAIL" | "NOT_RUN";
    readonly planSchemaValidated: boolean;
    readonly operationCount?: number;
    readonly reason?: string;
  };
  readonly evidenceSha256: string;
}

function canonicalize(value: unknown): string {
  if (Array.isArray(value)) {
    return "[" + value.map((item) => (item === undefined ? "null" : canonicalize(item))).join(",") + "]";
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return (
      "{" +
      Object.keys(record)
        .filter((key) => record[key] !== undefined)
        .sort()
        .map((key) => JSON.stringify(key) + ":" + canonicalize(record[key]))
        .join(",") +
      "}"
    );
  }
  if (value === undefined) return "null";
  return JSON.stringify(value);
}

export function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function sealEvidence(
  payload: Omit<ProductionEvidence, "evidenceSha256">,
): ProductionEvidence {
  const hash = sha256(canonicalize(payload));
  return { ...payload, evidenceSha256: hash };
}

export function verifyEvidenceSeal(evidence: ProductionEvidence): boolean {
  const { evidenceSha256, ...payload } = evidence;
  return evidenceSha256 === sha256(canonicalize(payload));
}

export async function writeProductionEvidence(
  evidenceDir: string,
  payload: Omit<ProductionEvidence, "evidenceSha256">,
): Promise<{ path: string; evidenceSha256: string }> {
  const sealed = sealEvidence(payload);
  const runsDir = join(evidenceDir, "runs");
  const path = join(runsDir, sealed.loopRunId + ".json");
  const tempPath = join(runsDir, "." + sealed.loopRunId + "." + randomUUID() + ".tmp");
  await mkdir(runsDir, { recursive: true });
  await writeFile(tempPath, JSON.stringify(sealed, null, 2) + "\n", "utf8");
  await rename(tempPath, path);
  return { path, evidenceSha256: sealed.evidenceSha256 };
}

export async function loadProductionHistory(
  evidenceDir: string,
): Promise<ProductionExecutionTelemetry[]> {
  const runsDir = join(evidenceDir, "runs");
  let names: string[] = [];
  try {
    names = await readdir(runsDir);
  } catch {
    return [];
  }

  const rows: ProductionExecutionTelemetry[] = [];
  for (const name of names.filter((item) => item.endsWith(".json")).sort()) {
    try {
      const parsed = JSON.parse(await readFile(join(runsDir, name), "utf8")) as ProductionEvidence;
      if (
        parsed.schemaVersion === "SCOS_GOVERNED_PRODUCTION_LOOP_R1" &&
        parsed.telemetry?.schemaVersion === "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1" &&
        verifyEvidenceSeal(parsed)
      ) {
        rows.push(parsed.telemetry);
      }
    } catch {
      // A malformed historical evidence file is never promoted into routing facts.
    }
  }
  return rows;
}

export function summarizeModelHistory(
  rows: readonly ProductionExecutionTelemetry[],
  providerId: string,
  modelId: string,
  contractRevision?: string,
): Pick<ProductionExecutionTelemetry, "status"> & {
  successRate?: number;
  observedLatencyMs?: number;
} {
  const matching = rows.filter(
    (row) =>
      row.providerId === providerId &&
      row.modelId === modelId &&
      (contractRevision === undefined || row.contractRevision === contractRevision),
  );
  if (matching.length === 0) return { status: "FAILED" };

  const successes = matching.filter((row) => row.status === "COMPLETED").length;
  const successRate = successes / matching.length;
  const latencyRows = matching.filter((row) => Number.isFinite(row.durationMs));
  const observedLatencyMs =
    latencyRows.length === 0
      ? undefined
      : latencyRows.reduce((sum, row) => sum + row.durationMs, 0) / latencyRows.length;

  return {
    status: successes === matching.length ? "COMPLETED" : "FAILED",
    successRate,
    observedLatencyMs,
  };
}
