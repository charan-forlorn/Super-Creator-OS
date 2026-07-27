/**
 * SCOS Cohort 10H — server-only paid-pilot delivery bridge.
 *
 * This module imports Node built-ins (child_process) and is imported ONLY by the
 * API route (server-side). It is NEVER imported by a client component.
 *
 * Bounded child_process transport to the Python authority:
 *   python -m scos.control_center.hvs_paid_pilot_delivery_cli <operation>
 *   - spawn with argv array (no shell interpolation)
 *   - canonical SCOS Python interpreter from trusted server config only
 *   - request over stdin as bounded JSON; one JSON response from stdout
 *   - malformed/empty/oversized output => failure
 *   - raw stderr/stack/paths NEVER returned to the browser
 *   - bounded timeout; kill only the owned child on stall
 *   - no automatic retry
 */

import * as childProcess from "node:child_process";
import * as nodeFs from "node:fs";
import { dirname, join, resolve as nodeResolve } from "node:path";

import type {
  BackupReceiptView,
  DeliveryRecordView,
  DeliveryResponse,
} from "./paid-pilot-types";

const BRIDGE_MODULE = "scos.control_center.hvs_paid_pilot_delivery_cli";
const MAX_STDOUT_BYTES = 1_048_576;
const BRIDGE_TIMEOUT_MS = 60_000;

function resolveTrustedDefaultPython(): string {
  return process.env.SCOS_PYTHON_INTERPRETER && process.env.SCOS_PYTHON_INTERPRETER.length > 0
    ? process.env.SCOS_PYTHON_INTERPRETER
    : nodeResolve(process.cwd(), "..", "..", ".venv", "Scripts", "python.exe");
}

function serverResolvedStorePath(): string | undefined {
  const p = process.env.SCOS_PAID_PILOT_DELIVERY_STORE_PATH;
  return p && p.length > 0 ? p : undefined;
}

export interface BridgePayload {
  operation: string;
  [key: string]: unknown;
}

function buildDeliveryPayload(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const storePath = serverResolvedStorePath();
  return storePath ? { store_path: storePath, ...extra } : { ...extra };
}

export function invokeBridge(payload: Record<string, unknown>): Promise<DeliveryResponse> {
  return new Promise((resolve) => {
    const python = resolveTrustedDefaultPython();
    // Detect repo root: prefer SCOS_REPO_ROOT env, else walk up from cwd to find scos/control_center
    let repoRoot = process.env.SCOS_REPO_ROOT;
    if (!repoRoot) {
      let cwd = process.cwd();
      for (let i = 0; i < 3; i++) {
        if (nodeFs.existsSync(join(cwd, "scos", "control_center"))) {
          repoRoot = cwd;
          break;
        }
        cwd = dirname(cwd);
      }
      if (!repoRoot) repoRoot = nodeResolve(process.cwd(), "..", "..");
    }
    const child = childProcess.spawn(
      python,
      ["-m", BRIDGE_MODULE, payload.operation as string],
      {
        cwd: repoRoot,
        env: { ...process.env, PYTHONPATH: repoRoot, PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1", TZ: "UTC" },
        windowsHide: true,
      },
    );
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* ignore */
      }
      resolve({
        ok: false,
        error_code: "BRIDGE_TIMEOUT",
        detail: "delivery bridge timed out",
        record: null,
        package_sha256: null,
        package_path: null,
        backup_receipt: null,
      });
    }, BRIDGE_TIMEOUT_MS);
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString("utf8");
      if (stdout.length > MAX_STDOUT_BYTES) {
        try {
          child.kill("SIGKILL");
        } catch {
          /* ignore */
        }
      }
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString("utf8");
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        error_code: "BRIDGE_SPAWN_FAILED",
        detail: err.message,
        record: null,
        package_sha256: null,
        package_path: null,
        backup_receipt: null,
      });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const body = stdout.trim();
      if (!body) {
        // Do NOT surface raw stderr to the browser. Log server-side only.
        console.error("[paid-pilot-bridge] empty output:", stderr.slice(0, 200));
        resolve({
          ok: false,
          error_code: "BRIDGE_EMPTY_OUTPUT",
          detail: "no response from delivery authority",
          record: null,
          package_sha256: null,
          package_path: null,
          backup_receipt: null,
        });
        return;
      }
      try {
        const parsed = JSON.parse(body) as Record<string, unknown>;
        // Browser-safe envelope: never expose absolute filesystem paths or
        // raw stderr. The authoritative package is fetched via the download
        // route using the delivery id, never by an absolute path.
        const record = parsed.record as DeliveryRecordView | null;
        if (record && typeof record === "object") {
          delete (record as unknown as Record<string, unknown>).package_path;
        }
        resolve({
          ok: Boolean(parsed.ok),
          error_code: (parsed.error_code as string | null) ?? null,
          detail: (parsed.detail as string | null) ?? null,
          record,
          package_sha256: (parsed.package_sha256 as string | null) ?? null,
          package_path: null,
          backup_receipt: (parsed.backup_receipt as BackupReceiptView | null) ?? null,
        });
      } catch {
        resolve({
          ok: false,
          error_code: "BRIDGE_MALFORMED_OUTPUT",
          detail: "json parse failed",
          record: null,
          package_sha256: null,
          package_path: null,
          backup_receipt: null,
        });
      }
    });
    const { operation, ...rest } = payload;
    child.stdin.write(JSON.stringify(rest));
    child.stdin.end();
  });
}

export async function submitRightsReview(opts: {
  deliveryId: string;
  projectId: string;
  operatorId: string;
  reviewedAt: string;
  entries: unknown[];
  attestation?: string;
}): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({
    operation: "rights-review",
    delivery_id: opts.deliveryId,
    project_id: opts.projectId,
    operator_id: opts.operatorId,
    reviewed_at: opts.reviewedAt,
    entries: opts.entries,
    attestation: opts.attestation ?? "",
  }));
}

export async function approveDelivery(opts: {
  deliveryId: string;
  operatorId: string;
  decidedAt: string;
  decision: "APPROVED_FOR_DELIVERY" | "REJECTED_REWORK_REQUIRED";
  sourceRenderAttemptId: string;
  artifactIdentity: string;
  artifactSha256: string;
  artifactSize: number;
  mediaProfile: string;
  qaRecordId: string;
  qaState: string;
  rightsRevision: string;
  rightsStatus: string;
  recordedAt: string;
}): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({
    operation: "approve",
    delivery_id: opts.deliveryId,
    operator_id: opts.operatorId,
    decided_at: opts.decidedAt,
    decision: opts.decision,
    source_render_attempt_id: opts.sourceRenderAttemptId,
    artifact_identity: opts.artifactIdentity,
    artifact_sha256: opts.artifactSha256,
    artifact_size: opts.artifactSize,
    media_profile: opts.mediaProfile,
    qa_record_id: opts.qaRecordId,
    qa_state: opts.qaState,
    rights_revision: opts.rightsRevision,
    rights_status: opts.rightsStatus,
    recorded_at: opts.recordedAt,
  }));
}

export async function createDeliveryPackage(opts: {
  deliveryId: string;
  projectId: string;
  hvsProjectId: string;
  attemptId: string;
  profileId: string;
  qaReportId: string;
  artifactPath: string;
  operatorId: string;
  recordedAt: string;
  rightsRevision: string;
  rightsStatus: string;
  retentionClass: string;
}): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({
    operation: "create-package",
    delivery_id: opts.deliveryId,
    project_id: opts.projectId,
    hvs_project_id: opts.hvsProjectId,
    attempt_id: opts.attemptId,
    profile_id: opts.profileId,
    qa_report_id: opts.qaReportId,
    artifact_path: opts.artifactPath,
    operator_id: opts.operatorId,
    recorded_at: opts.recordedAt,
    rights_revision: opts.rightsRevision,
    rights_status: opts.rightsStatus,
    retention_class: opts.retentionClass,
  }));
}

export async function runQa(opts: {
  deliveryId: string;
  qaReportId: string;
  qaState: string;
  artifactId: string;
  artifactSha256: string;
  recordedAt: string;
}): Promise<DeliveryResponse> {
  return invokeBridge(
    buildDeliveryPayload({
      operation: "qa",
      delivery_id: opts.deliveryId,
      qa_report_id: opts.qaReportId,
      qa_state: opts.qaState,
      artifact_id: opts.artifactId,
      artifact_sha256: opts.artifactSha256,
      recorded_at: opts.recordedAt,
    }),
  );
}

export async function markHandoffReady(deliveryId: string): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({ operation: "mark-handoff-ready", delivery_id: deliveryId }));
}

export async function getDelivery(deliveryId: string): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({ operation: "get", delivery_id: deliveryId }));
}

export async function listDeliveries(): Promise<DeliveryResponse> {
  return invokeBridge(buildDeliveryPayload({ operation: "list" }));
}