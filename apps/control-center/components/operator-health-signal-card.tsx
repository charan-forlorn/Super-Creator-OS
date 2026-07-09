import { getSignalTone } from "@/lib/operator-read-surface-projection";
import type { OperatorHealthSignal } from "@/lib/operator-read-surface-types";

function labelFor(signalType: OperatorHealthSignal["signalType"]): string {
  return signalType.replaceAll("_", " ");
}

export function OperatorHealthSignalCard({
  signal,
}: {
  signal: OperatorHealthSignal;
}) {
  const hints = [...signal.blockers, ...signal.warnings];
  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-ink">
            {labelFor(signal.signalType)}
          </h4>
          <p className="mt-1 text-[11px] text-ink-faint">{signal.sourceStage}</p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${getSignalTone(signal.status)}`}
        >
          {signal.status}
        </span>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-muted">
        {signal.summary}
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          severity {signal.severity}
        </span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          refs {signal.references.length}
        </span>
      </div>

      {hints.length > 0 ? (
        <ul className="mt-3 space-y-1">
          {hints.map((hint) => (
            <li
              key={hint}
              className="rounded-md bg-status-review/10 px-2 py-1 text-[11px] text-status-review"
            >
              {hint}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[11px] text-ink-faint">No warning or blocker hint.</p>
      )}
    </article>
  );
}
