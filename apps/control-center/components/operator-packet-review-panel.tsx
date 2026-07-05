"use client";

import { useMemo, useState } from "react";

import { PacketApprovalDecisionPanel } from "./packet-approval-decision-panel";
import { PacketReviewCard } from "./packet-review-card";
import { ManualHandoffPanel } from "./manual-handoff-panel";
import type {
  OperatorPacketDecision,
  OperatorPacketReviewView,
} from "@/lib/operator-packet-review-types";

export function OperatorPacketReviewPanel({
  reviews,
}: {
  reviews: readonly OperatorPacketReviewView[];
}) {
  const [selectedReviewId, setSelectedReviewId] = useState(reviews[0]?.reviewId ?? "");
  const [localDecisions, setLocalDecisions] = useState<
    Record<string, OperatorPacketDecision>
  >({});

  const selectedReview = useMemo(
    () => reviews.find((review) => review.reviewId === selectedReviewId) ?? reviews[0],
    [reviews, selectedReviewId],
  );

  const selectedDecision = selectedReview
    ? localDecisions[selectedReview.reviewId] ?? null
    : null;

  function handleDecision(decision: OperatorPacketDecision) {
    if (!selectedReview) return;
    setLocalDecisions((current) => ({
      ...current,
      [selectedReview.reviewId]: decision,
    }));
  }

  const pendingCount = reviews.filter((review) => review.status === "pending").length;
  const blockedCount = reviews.filter((review) => review.status === "blocked").length;
  const handoffCount = reviews.filter(
    (review) => review.status === "manual_handoff_prepared",
  ).length;

  if (!selectedReview) {
    return (
      <section className="rounded-card border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-ink">Operator Packet Review</h2>
        <p className="mt-2 text-xs text-ink-faint">No packet reviews are queued.</p>
      </section>
    );
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Operator Packet Review</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Stage 5.5 local review queue. Operator approval is required before
            any future dispatch integration can act.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] font-semibold">
          <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-status-review ring-1 ring-inset ring-status-review/30">
            {pendingCount} pending
          </span>
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-accent ring-1 ring-inset ring-accent/30">
            {handoffCount} handoff
          </span>
          <span className="rounded-full bg-status-blocked/15 px-2 py-0.5 text-status-blocked ring-1 ring-inset ring-status-blocked/30">
            {blockedCount} blocked
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.3fr)]">
        <div className="space-y-2">
          {reviews.map((review) => (
            <PacketReviewCard
              key={review.reviewId}
              review={review}
              selected={review.reviewId === selectedReview.reviewId}
              onSelect={setSelectedReviewId}
            />
          ))}
        </div>

        <div className="space-y-3">
          <section className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
                {selectedReview.reviewId}
              </span>
              <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-[10px] font-semibold text-status-review ring-1 ring-inset ring-status-review/30">
                {selectedReview.routingPriority}
              </span>
              {selectedReview.verdict ? (
                <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink-muted ring-1 ring-inset ring-border">
                  {selectedReview.verdict}
                </span>
              ) : null}
            </div>
            <h3 className="mt-3 text-sm font-semibold text-ink">
              {selectedReview.title}
            </h3>
            <p className="mt-1 text-xs text-ink-muted">{selectedReview.objective}</p>
            <p className="mt-2 rounded bg-surface px-3 py-2 text-xs text-ink-muted">
              Routing recommendation: {selectedReview.sourceAgent} -&gt;{" "}
              <span className="font-semibold text-ink">{selectedReview.targetAgent}</span>{" "}
              ({selectedReview.targetRuntimeId}). {selectedReview.routingReason}
            </p>
            <p className="mt-2 text-[11px] text-ink-faint">
              No packet is automatically dispatched. Manual handoff is local-only
              and must be performed by the operator outside SCOS.
            </p>
          </section>

          <PacketApprovalDecisionPanel
            review={selectedReview}
            selectedDecision={selectedDecision}
            onDecision={handleDecision}
          />

          {selectedDecision ? (
            <p className="rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2 text-xs text-ink-muted">
              Local mock decision selected:{" "}
              <span className="font-semibold text-ink">
                {selectedDecision.replace(/_/g, " ")}
              </span>
              . This is not stored and does not call the backend.
            </p>
          ) : null}

          <ManualHandoffPanel review={selectedReview} />
        </div>
      </div>
    </section>
  );
}
