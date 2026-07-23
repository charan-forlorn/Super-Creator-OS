"use client";

/**
 * SCOS Cohort 10H — Paid-Pilot Delivery Panel (no-terminal authority view).
 *
 * The browser is projection + deliberate operator action only. Every business
 * transition is confirmed by the authoritative server response before the UI
 * advances. No optimistic state, no browser storage, no HVS call, no polling
 * loop, no automatic retry.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getDelivery,
  approveDelivery,
  createDeliveryPackage,
  markHandoffReady,
  readDeliveryProjection,
  submitRightsReview,
} from "@/lib/paid-pilot-delivery-client";
import type {
  DeliveryRecordView,
  DeliveryState,
  DeliveryTruthState,
  RightsChecklistEntryView,
  RightsState,
} from "@/lib/paid-pilot-types";

interface RightsEntryDraft {
  asset_kind: string;
  description: string;
  known_source: boolean;
  permitted: boolean;
  attribution_note: string;
}

const EMPTY_RIGHTS: RightsEntryDraft = {
  asset_kind: "visual",
  description: "",
  known_source: true,
  permitted: true,
  attribution_note: "",
};

function stateTone(state: string): string {
  if (state.startsWith("DELIVERY_APPROVED") || state === "DELIVERY_READY_FOR_MANUAL_HANDOFF" || state === "DELIVERY_PACKAGE_READY" || state === "DELIVERY_BACKUP_READY") {
    return "text-status-review";
  }
  if (state.startsWith("DELIVERY_BLOCKED") || state === "DELIVERY_REJECTED" || state === "DELIVERY_PACKAGE_FAILED_CONFIRMED" || state === "DELIVERY_PACKAGE_CORRUPT") {
    return "text-status-failed";
  }
  return "text-status-waiting";
}

export function PaidPilotDeliveryPanel() {
  const [deliveryId, setDeliveryId] = useState<string>("");
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [truth, setTruth] = useState<DeliveryTruthState | null>(null);
  const [record, setRecord] = useState<DeliveryRecordView | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // synthetic paid-pilot identity (operator fills / accepts)
  const [projectId, setProjectId] = useState<string>("spp-paidpilot-10h");
  const [rightsEntries, setRightsEntries] = useState<RightsEntryDraft[]>([EMPTY_RIGHTS]);
  const [rightsReviewed, setRightsReviewed] = useState(false);
  const requestSeq = useRef(0);

  const refresh = useCallback((id: string) => {
    const seq = ++requestSeq.current;
    setLoadState("loading");
    readDeliveryProjection(id)
      .then((proj) => {
        if (seq !== requestSeq.current) return;
        setTruth(proj.status);
        setRecord(proj.record);
        setErrorCode(null);
        setDetail(null);
        setObservedAt(new Date().toISOString());
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        setTruth("UNAVAILABLE");
        setRecord(null);
        setErrorCode("READ_FAILED");
        setDetail(err instanceof Error ? err.message : "unknown");
        setLoadState("ready");
      });
  }, []);

  useEffect(() => {
    if (deliveryId) refresh(deliveryId);
    else setLoadState("ready");
  }, [deliveryId, refresh]);

  async function handleRightsReview() {
    setPending(true);
    setFeedback(null);
    try {
      const entries: RightsChecklistEntryView[] = rightsEntries.map((e) => ({
        asset_kind: e.asset_kind,
        description: e.description,
        known_source: e.known_source,
        permitted: e.permitted,
        attribution_note: e.attribution_note,
      }));
      const res = await submitRightsReview({
        deliveryId: `scos-hvs-pp-delivery-${projectId}`,
        projectId,
        operatorId: "local-solo-operator",
        reviewedAt: new Date().toISOString(),
        entries,
        attestation: "Operator attests all listed assets have known source and permitted use.",
      });
      if (!res.ok || !res.record) {
        setErrorCode(res.error_code);
        setDetail(res.detail);
        setFeedback(`Rights review failed: ${res.error_code}`);
        return;
      }
      setRightsReviewed(true);
      setDeliveryId(res.record.delivery_id);
      refresh(res.record.delivery_id);
      setFeedback(`Rights status: ${res.record.rights_status}`);
    } finally {
      setPending(false);
    }
  }

  async function handleApprove(decision: "APPROVED_FOR_DELIVERY" | "REJECTED_REWORK_REQUIRED") {
    if (!record) return;
    setPending(true);
    setFeedback(null);
    try {
      const res = await approveDelivery({
        deliveryId: record.delivery_id,
        operatorId: "local-solo-operator",
        decidedAt: new Date().toISOString(),
        decision,
        sourceRenderAttemptId: record.source_render_attempt_id,
        artifactIdentity: record.artifact_identity,
        artifactSha256: record.artifact_sha256,
        artifactSize: record.artifact_size,
        mediaProfile: record.media_profile,
        qaRecordId: record.qa_record_id,
        qaState: record.qa_state,
        rightsRevision: record.rights_checklist_revision,
        rightsStatus: record.rights_status,
        recordedAt: record.created_at,
      });
      if (!res.ok || !res.record) {
        setErrorCode(res.error_code);
        setDetail(res.detail);
        setFeedback(`Approval failed: ${res.error_code}`);
        return;
      }
      setRecord(res.record);
      refresh(res.record.delivery_id);
      setFeedback(`Decision: ${decision}`);
    } finally {
      setPending(false);
    }
  }

  async function handleCreatePackage() {
    if (!record) return;
    setPending(true);
    setFeedback(null);
    try {
      const res = await createDeliveryPackage({
        deliveryId: record.delivery_id,
        projectId: record.project_id,
        hvsProjectId: record.project_id,
        attemptId: record.source_render_attempt_id,
        profileId: record.media_profile,
        qaReportId: record.qa_record_id,
        artifactPath: "", // server-resolved from authoritative QA/artifact record
        operatorId: "local-solo-operator",
        recordedAt: new Date().toISOString(),
        rightsRevision: record.rights_checklist_revision,
        rightsStatus: record.rights_status,
        retentionClass: record.retention_class,
      });
      if (!res.ok || !res.record) {
        setErrorCode(res.error_code);
        setDetail(res.detail);
        setFeedback(`Package failed: ${res.error_code}`);
        return;
      }
      setRecord(res.record);
      refresh(res.record.delivery_id);
      setFeedback(`Package ${res.record.state} (sha256 ${res.package_sha256?.slice(0, 12)}…)`);
    } finally {
      setPending(false);
    }
  }

  async function handleMarkHandoff() {
    if (!record) return;
    setPending(true);
    setFeedback(null);
    try {
      const res = await markHandoffReady(record.delivery_id);
      if (!res.ok || !res.record) {
        setErrorCode(res.error_code);
        setDetail(res.detail);
        setFeedback(`Handoff failed: ${res.error_code}`);
        return;
      }
      setRecord(res.record);
      refresh(res.record.delivery_id);
      setFeedback(`Status: ${res.record.state}`);
    } finally {
      setPending(false);
    }
  }

  function handleDownload() {
    if (!record) return;
    window.open(`/api/paid-pilot/delivery/download?deliveryId=${encodeURIComponent(record.delivery_id)}`, "_blank");
  }

  const canApprove = record?.rights_status === "RIGHTS_APPROVED" && record?.qa_state === "QA_PASSED";
  const canPackage = record?.operator_decision === "APPROVED_FOR_DELIVERY";
  const canDownload = record != null && ["DELIVERY_PACKAGE_READY", "DELIVERY_BACKUP_READY", "DELIVERY_READY_FOR_MANUAL_HANDOFF"].includes(record.state);

  return (
    <section className="cockpit-panel">
      <div className="panel-heading">
        <div>
          <h2>Paid-Pilot Delivery</h2>
          <p>Durable, no-terminal delivery ownership. Browser is projection only.</p>
        </div>
        {truth && (
          <span className="cockpit-note cockpit-note--live">
            store: {truth}
          </span>
        )}
      </div>

      <div className="route-toolbar">
        <label className="text-[11px] uppercase tracking-wide text-muted">
          Synthetic project id
          <input
            className="mt-1 w-full rounded border border-border-soft px-2 py-1 text-sm"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={pending}
          />
        </label>
      </div>

      {/* Rights checklist */}
      <div className="mt-3">
        <h3 className="text-sm font-semibold">Asset rights checklist</h3>
        {rightsEntries.map((entry, idx) => (
          <div key={idx} className="mt-2 rounded border border-border-soft p-2 text-xs">
            <input
              className="w-full rounded px-1 py-0.5"
              placeholder="asset description"
              value={entry.description}
              onChange={(e) => {
                const copy = [...rightsEntries];
                copy[idx] = { ...copy[idx], description: e.target.value };
                setRightsEntries(copy);
              }}
            />
            <label className="mt-1 flex items-center gap-2">
              <input
                type="checkbox"
                checked={entry.known_source}
                onChange={(e) => {
                  const copy = [...rightsEntries];
                  copy[idx] = { ...copy[idx], known_source: e.target.checked };
                  setRightsEntries(copy);
                }}
              />
              known source
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={entry.permitted}
                onChange={(e) => {
                  const copy = [...rightsEntries];
                  copy[idx] = { ...copy[idx], permitted: e.target.checked };
                  setRightsEntries(copy);
                }}
              />
              permitted for use
            </label>
          </div>
        ))}
        <button
          type="button"
          className="button-secondary mt-2"
          disabled={pending}
          onClick={() => setRightsEntries([...rightsEntries, EMPTY_RIGHTS])}
        >
          Add asset
        </button>
        <button
          type="button"
          className="button-primary mt-2 ml-2"
          disabled={pending || !projectId}
          onClick={handleRightsReview}
        >
          Submit rights review
        </button>
      </div>

      {/* Record projection */}
      {loadState === "loading" && <p className="empty-state">Loading authoritative state…</p>}
      {loadState === "ready" && record && (
        <div className="mt-3 rounded border border-border-soft p-2 text-xs">
          <div className="flex items-center gap-2">
            <span className={`rounded-full border border-border-soft px-2 py-0.5 font-semibold ${stateTone(record.state)}`}>
              {record.state}
            </span>
            <span className="text-muted">rights: {record.rights_status}</span>
            <span className="text-muted">qa: {record.qa_state}</span>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-1">
            <div><dt className="text-muted">delivery id</dt><dd className="break-all">{record.delivery_id}</dd></div>
            <div><dt className="text-muted">artifact sha256</dt><dd className="break-all">{record.artifact_sha256.slice(0, 16)}…</dd></div>
            <div><dt className="text-muted">package sha256</dt><dd className="break-all">{record.package_sha256 ? record.package_sha256.slice(0, 16) + "…" : "—"}</dd></div>
            <div><dt className="text-muted">backup</dt><dd>{record.backup_receipt ? record.backup_receipt.backup_id : "—"}</dd></div>
          </dl>
        </div>
      )}
      {loadState === "ready" && !record && truth === "EMPTY" && (
        <p className="empty-state">No delivery record yet. Submit a rights review to begin.</p>
      )}

      {/* Actions */}
      <div className="action-buttons mt-3">
        <button
          type="button"
          className="button-primary"
          disabled={pending || !canApprove}
          onClick={() => handleApprove("APPROVED_FOR_DELIVERY")}
        >
          Approve for delivery
        </button>
        <button
          type="button"
          className="button-danger"
          disabled={pending || !canApprove}
          onClick={() => handleApprove("REJECTED_REWORK_REQUIRED")}
        >
          Reject / rework
        </button>
        <button
          type="button"
          className="button-secondary"
          disabled={pending || !canPackage}
          onClick={handleCreatePackage}
        >
          Generate package
        </button>
        <button
          type="button"
          className="button-secondary"
          disabled={pending || record?.state !== "DELIVERY_PACKAGE_READY"}
          onClick={handleMarkHandoff}
        >
          Mark ready for handoff
        </button>
        <button
          type="button"
          className="button-primary"
          disabled={!canDownload}
          onClick={handleDownload}
        >
          Download package
        </button>
      </div>

      {feedback && <p className="mt-2 text-[11px] font-semibold text-status-review">{feedback}</p>}
      {errorCode && <p className="mt-1 text-[11px] font-semibold text-status-failed">{errorCode}: {detail}</p>}
    </section>
  );
}
