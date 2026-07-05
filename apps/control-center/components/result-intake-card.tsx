import { cn } from "@/lib/utils";
import type { AIResultIntakeRecordView, ResultVerdict } from "@/lib/result-intake-types";

const VERDICT_STYLES: Record<ResultVerdict, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  BLOCKED: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  NEEDS_FIX: "bg-status-working/15 text-status-working ring-status-working/30",
  NEEDS_REVIEW: "bg-status-review/15 text-status-review ring-status-review/30",
  PARTIAL: "bg-status-review/15 text-status-review ring-status-review/30",
  UNKNOWN: "bg-status-idle/15 text-ink-muted ring-status-idle/25",
};

const SOURCE_AGENT_LABEL: Record<AIResultIntakeRecordView["sourceAgent"], string> = {
  chatgpt: "ChatGPT",
  claude_code: "Claude Code",
  codex: "Codex",
  hermes: "Hermes",
  operator: "Operator (manual)",
};

export function VerdictBadge({ verdict, className }: { verdict: ResultVerdict; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
        VERDICT_STYLES[verdict],
        className,
      )}
    >
      {verdict}
    </span>
  );
}

export function ResultIntakeCard({
  intake,
  selected,
  onSelect,
}: {
  intake: AIResultIntakeRecordView;
  selected: boolean;
  onSelect: (intakeId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(intake.intakeId)}
      className={cn(
        "w-full rounded-lg border px-3 py-2.5 text-left transition-colors",
        selected
          ? "border-accent/40 bg-accent/10 ring-1 ring-inset ring-accent/30"
          : "border-border-soft bg-surface-2/30 hover:bg-surface-2/60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
          {intake.intakeId}
        </span>
        <VerdictBadge verdict={intake.verdict} />
        {intake.operatorReviewRequired ? (
          <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-[10px] font-semibold text-status-review ring-1 ring-inset ring-status-review/30">
            review required
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-xs font-semibold text-ink">{intake.title}</p>
      <p className="mt-1 text-[11px] text-ink-faint">
        {SOURCE_AGENT_LABEL[intake.sourceAgent]} · {intake.sourceRuntimeId} · {intake.taskId}
      </p>
      <p className="mt-1.5 line-clamp-2 text-[11px] text-ink-muted">{intake.normalizedSummary}</p>
    </button>
  );
}
