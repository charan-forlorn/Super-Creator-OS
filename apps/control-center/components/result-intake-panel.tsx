"use client";

import { useMemo } from "react";

import { ResultIntakeCard, VerdictBadge } from "./result-intake-card";
import type { AIResultIntakeRecordView } from "@/lib/result-intake-types";

const SOURCE_AGENT_LABEL: Record<AIResultIntakeRecordView["sourceAgent"], string> = {
  chatgpt: "ChatGPT",
  claude_code: "Claude Code",
  codex: "Codex",
  hermes: "Hermes",
  operator: "Operator (manual)",
};

export function ResultIntakePanel({
  intakes,
  selectedIntakeId,
  onSelectIntake,
}: {
  intakes: readonly AIResultIntakeRecordView[];
  selectedIntakeId: string;
  onSelectIntake: (intakeId: string) => void;
}) {
  const selected = useMemo(
    () => intakes.find((intake) => intake.intakeId === selectedIntakeId) ?? intakes[0],
    [intakes, selectedIntakeId],
  );

  const reviewRequiredCount = intakes.filter((intake) => intake.operatorReviewRequired).length;
  const blockedCount = intakes.filter((intake) => intake.verdict === "BLOCKED").length;

  if (!selected) {
    return (
      <section className="rounded-card border border-border bg-surface p-4">
        <h2 className="text-sm font-semibold text-ink">Result Intake</h2>
        <p className="mt-2 text-xs text-ink-faint">No agent or operator results have been pasted in yet.</p>
      </section>
    );
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Result Intake</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Stage 5.7 manual-handoff intake. Results are pasted in by the operator; nothing
            here is fetched, dispatched, or read from a clipboard automatically.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] font-semibold">
          <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-status-review ring-1 ring-inset ring-status-review/30">
            {reviewRequiredCount} review required
          </span>
          <span className="rounded-full bg-status-blocked/15 px-2 py-0.5 text-status-blocked ring-1 ring-inset ring-status-blocked/30">
            {blockedCount} blocked
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(280px,0.9fr)_minmax(0,1.3fr)]">
        <div className="space-y-2">
          {intakes.map((intake) => (
            <ResultIntakeCard
              key={intake.intakeId}
              intake={intake}
              selected={intake.intakeId === selected.intakeId}
              onSelect={onSelectIntake}
            />
          ))}
        </div>

        <div className="space-y-3">
          <section className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
                {selected.intakeId}
              </span>
              <VerdictBadge verdict={selected.verdict} />
              <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink-muted ring-1 ring-inset ring-border">
                confidence: {selected.confidence}
              </span>
            </div>
            <h3 className="mt-3 text-sm font-semibold text-ink">{selected.title}</h3>
            <p className="mt-1 text-xs text-ink-muted">
              {SOURCE_AGENT_LABEL[selected.sourceAgent]} · {selected.sourceRuntimeId} ·{" "}
              {selected.sessionId} / {selected.taskId}
            </p>
            <p className="mt-2 rounded bg-surface px-3 py-2 text-xs text-ink-muted">
              {selected.normalizedSummary}
            </p>

            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded bg-surface px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                  Blockers
                </p>
                {selected.blockers.length ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-status-blocked">
                    {selected.blockers.map((blocker) => (
                      <li key={blocker}>{blocker}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-[11px] text-ink-faint">None</p>
                )}
              </div>
              <div className="rounded bg-surface px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                  Warnings
                </p>
                {selected.warnings.length ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-status-working">
                    {selected.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-[11px] text-ink-faint">None</p>
                )}
              </div>
            </div>

            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <p className="rounded bg-surface px-3 py-2 text-[11px] text-ink-muted">
                <span className="font-semibold text-ink">Tests:</span> {selected.testsSummary || "Not reported"}
              </p>
              <p className="rounded bg-surface px-3 py-2 text-[11px] text-ink-muted">
                <span className="font-semibold text-ink">Changed Files:</span>{" "}
                {selected.changedFilesSummary || "Not reported"}
              </p>
            </div>

            {selected.artifacts.length ? (
              <div className="mt-2 rounded bg-surface px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                  Artifacts / Evidence
                </p>
                <ul className="mt-1 space-y-1">
                  {selected.artifacts.map((artifact) => (
                    <li key={artifact.artifactId} className="text-[11px] text-ink-muted">
                      <span className="font-semibold text-ink">{artifact.title}</span>{" "}
                      <span className="text-ink-faint">({artifact.artifactType}{artifact.required ? ", required" : ""})</span>
                      {" — "}
                      {artifact.summary}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="mt-2 text-[11px] text-ink-faint">
              {selected.operatorReviewRequired
                ? "Operator review is required before this result can move forward."
                : "No operator review flag was raised for this result."}
            </p>
          </section>
        </div>
      </div>
    </section>
  );
}
