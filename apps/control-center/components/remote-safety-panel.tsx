import { cn } from "@/lib/utils";
import type { RemoteSafetyCheck, RemoteSafetyVerdict, TestEvidenceResult } from "@/lib/types";

const VERDICT_STYLES: Record<RemoteSafetyVerdict, string> = {
  REMOTE_SAFE: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  REMOTE_BLOCKED: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  NEEDS_REVIEW: "bg-status-working/15 text-status-working ring-status-working/30",
};

const RESULT_STYLES: Record<TestEvidenceResult, string> = {
  PASS: "text-status-approved",
  FAIL: "text-status-blocked",
  MISSING: "text-status-blocked",
  SKIPPED: "text-ink-faint",
};

export function RemoteSafetyPanel({ check }: { check: RemoteSafetyCheck }) {
  return (
    <section className="rounded-xl border border-border-soft bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Remote Safety Check</h3>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
            VERDICT_STYLES[check.verdict],
          )}
        >
          {check.verdict}
        </span>
      </div>

      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-surface-2/50 p-2.5">
          <dt className="text-[11px] text-ink-faint">Branch</dt>
          <dd className="font-medium text-ink">{check.branch}</dd>
        </div>
        <div className="rounded-lg bg-surface-2/50 p-2.5">
          <dt className="text-[11px] text-ink-faint">Local ahead</dt>
          <dd className="font-medium text-ink">{check.localAheadCommits}</dd>
        </div>
        <div className="rounded-lg bg-surface-2/50 p-2.5">
          <dt className="text-[11px] text-ink-faint">Remote-only</dt>
          <dd className="font-medium text-ink">{check.remoteOnlyCommits}</dd>
        </div>
        <div className="rounded-lg bg-surface-2/50 p-2.5">
          <dt className="text-[11px] text-ink-faint">Working tree</dt>
          <dd className="font-medium text-ink">{check.workingTree}</dd>
        </div>
      </dl>

      <ul className="mt-3 space-y-1.5">
        {check.evidence.map((item) => (
          <li
            key={item.id}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2 text-xs"
          >
            <span className={cn("font-semibold", RESULT_STYLES[item.result])}>
              {item.result}
            </span>
            <span className="font-medium text-ink">{item.label}</span>
            <span className="text-ink-faint">{item.value}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
