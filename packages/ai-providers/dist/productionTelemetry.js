import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";
function canonicalize(value) {
    if (Array.isArray(value)) {
        return "[" + value.map((item) => (item === undefined ? "null" : canonicalize(item))).join(",") + "]";
    }
    if (value && typeof value === "object") {
        const record = value;
        return ("{" +
            Object.keys(record)
                .filter((key) => record[key] !== undefined)
                .sort()
                .map((key) => JSON.stringify(key) + ":" + canonicalize(record[key]))
                .join(",") +
            "}");
    }
    if (value === undefined)
        return "null";
    return JSON.stringify(value);
}
export function sha256(value) {
    return createHash("sha256").update(value, "utf8").digest("hex");
}
export function sealEvidence(payload) {
    const hash = sha256(canonicalize(payload));
    return { ...payload, evidenceSha256: hash };
}
export function verifyEvidenceSeal(evidence) {
    const { evidenceSha256, ...payload } = evidence;
    return evidenceSha256 === sha256(canonicalize(payload));
}
export async function writeProductionEvidence(evidenceDir, payload) {
    const sealed = sealEvidence(payload);
    const runsDir = join(evidenceDir, "runs");
    const path = join(runsDir, sealed.loopRunId + ".json");
    const tempPath = join(runsDir, "." + sealed.loopRunId + "." + randomUUID() + ".tmp");
    await mkdir(runsDir, { recursive: true });
    await writeFile(tempPath, JSON.stringify(sealed, null, 2) + "\n", "utf8");
    await rename(tempPath, path);
    return { path, evidenceSha256: sealed.evidenceSha256 };
}
export async function loadProductionHistory(evidenceDir) {
    const runsDir = join(evidenceDir, "runs");
    let names = [];
    try {
        names = await readdir(runsDir);
    }
    catch {
        return [];
    }
    const rows = [];
    for (const name of names.filter((item) => item.endsWith(".json")).sort()) {
        try {
            const parsed = JSON.parse(await readFile(join(runsDir, name), "utf8"));
            if (parsed.schemaVersion === "SCOS_GOVERNED_PRODUCTION_LOOP_R1" &&
                parsed.telemetry?.schemaVersion === "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1" &&
                verifyEvidenceSeal(parsed)) {
                rows.push(parsed.telemetry);
            }
        }
        catch {
            // A malformed historical evidence file is never promoted into routing facts.
        }
    }
    return rows;
}
export function summarizeModelHistory(rows, providerId, modelId, contractRevision) {
    const matching = rows.filter((row) => row.providerId === providerId &&
        row.modelId === modelId &&
        (contractRevision === undefined || row.contractRevision === contractRevision));
    if (matching.length === 0)
        return { status: "FAILED" };
    const successes = matching.filter((row) => row.status === "COMPLETED").length;
    const successRate = successes / matching.length;
    const latencyRows = matching.filter((row) => Number.isFinite(row.durationMs));
    const observedLatencyMs = latencyRows.length === 0
        ? undefined
        : latencyRows.reduce((sum, row) => sum + row.durationMs, 0) / latencyRows.length;
    return {
        status: successes === matching.length ? "COMPLETED" : "FAILED",
        successRate,
        observedLatencyMs,
    };
}
