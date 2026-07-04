"use client";

import { useState } from "react";

import { ChangedFilesReview } from "./changed-files-review";
import { CommitPlanPreview } from "./commit-plan-preview";
import { CommitReadinessChecklist } from "./commit-readiness-checklist";
import { RemoteSafetyPanel } from "./remote-safety-panel";
import { TestEvidencePanel } from "./test-evidence-panel";
import {
  decisionLabel,
  isCommitReady,
  isPushReady,
} from "@/lib/review-gates";
import { cn, getTaskById } from "@/lib/utils";
import type {
  OperatorDecision,
  OperatorReviewGate,
  ReviewGateStatus,
  ReviewGateVerdict,
} from "@/lib/types";

const STATUS_STYLES: Record<ReviewGateStatus, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  BLOCKED: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  NEEDS_FIX: "bg-status-working/15 text-status-working ring-status-working/30",
  WAITING: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

const VERDICT_STYLES: Record<ReviewGateVerdict, string> = {
  COMMIT_READY: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  HOLD: "bg-status-working/15 text-status-working ring-status-working/30",
  REQUEST_FIX: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  REJECT: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  WAITING_FOR_REVIEW: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

const LOCAL_DECISIONS: Array<{
  label: string;
  value: OperatorDecision;
  tone: string;
}> = [
  {
    label: "Approve Commit",
    value: "approve_commit",
    tone: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  },
  {
    label: "Request Fix",
    value: "request_fix",
    tone: "bg-status-working/15 text-status-working ring-status-working/30",
  },
  {
    label: "Hold",
    value: "hold",
    tone: "bg-surface-2 text-ink-muted ring-border",
  },
  {
    label: "Reject",
    value: "reject",
    tone: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  },
  {
    label: "Approve Push",
    value: "approve_push",
    tone: "bg-accent/15 text-accent ring-accent/30",
  },
];

export function OperatorReviewGate({ gate }: { gate: OperatorReviewGate }) {
  const [decision, setDecision] = useState<OperatorDecision>("none");
  const task = getTaskById(gate.reviewedTaskId);
  const commitReady = isCommitReady(gate);
  const pushReady = isPushReady(gate);

  function canUseDecision(value: OperatorDecision): boolean {
    if (value === "approve_commit") return commitReady;
    if (value === "approve_push") return pushReady;
    return value !== "none";
  }

  return (
    <section className="rounded-card border border-accent/30 bg-gradient-to-br from-surface-2 to-surface p-5 shadow-lg shadow-accent/5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-ink">
              Operator Review Gate
            </h2>
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                STATUS_STYLES[gate.reviewStatus],
              )}
            >
              {gate.reviewStatus}
            </span>
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                VERDICT_STYLES[gate.gateVerdict],
              )}
            >
              {gate.gateVerdict}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            {gate.reviewSummary}
          </p>
          <p className="mt-2 text-sm font-medium text-ink">
            {gate.recommendedOperatorAction}
          </p>
        </div>

        <dl className="grid shrink-0 gap-2 text-sm sm:grid-cols-3 lg:w-[28rem]">
          <div className="rounded-lg border border-border-soft bg-surface/70 p-3">
            <dt className="text-[11px] text-ink-faint">Reviewer</dt>
            <dd className="font-medium text-ink">{gate.reviewer}</dd>
          </div>
          <div className="rounded-lg border border-border-soft bg-surface/70 p-3">
            <dt className="text-[11px] text-ink-faint">Reviewed task</dt>
            <dd className="font-medium text-ink">
              {task ? `${task.code}` : gate.reviewedTaskId}
            </dd>
          </div>
          <div className="rounded-lg border border-border-soft bg-surface/70 p-3">
            <dt className="text-[11px] text-ink-faint">Local decision</dt>
            <dd className="font-medium text-ink">{decisionLabel(decision)}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-5 grid gap-4 2xl:grid-cols-2">
        <ChangedFilesReview files={gate.changedFiles} />
        <TestEvidencePanel evidence={gate.testEvidence} />
        <CommitReadinessChecklist items={gate.checklist} />
        <CommitPlanPreview plan={gate.commitPlan} />
      </div>

      <div className="mt-4">
        <RemoteSafetyPanel check={gate.remoteSafety} />
      </div>

      <div className="mt-4 rounded-xl border border-border-soft bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">Push Decision</h3>
            <p className="mt-1 text-xs text-ink-muted">
              Buttons are local-only and never stage, commit, push, or call git.
            </p>
          </div>
          <div className="grid w-full gap-2 sm:grid-cols-5 lg:w-auto">
            {LOCAL_DECISIONS.map((item) => {
              const enabled = canUseDecision(item.value);
              return (
                <button
                  key={item.value}
                  type="button"
                  disabled={!enabled}
                  aria-disabled={!enabled}
                  onClick={() => setDecision(item.value)}
                  className={cn(
                    "rounded-lg px-3 py-2 text-xs font-semibold ring-1 ring-inset transition-colors",
                    enabled
                      ? item.tone
                      : "cursor-not-allowed bg-surface-2 text-ink-faint opacity-55 ring-border",
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
