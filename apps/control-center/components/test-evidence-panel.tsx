import { cn } from "@/lib/utils";
import type { TestEvidence, TestEvidenceResult } from "@/lib/types";

const RESULT_STYLES: Record<TestEvidenceResult, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  MISSING: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  SKIPPED: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

export function TestEvidencePanel({ evidence }: { evidence: TestEvidence[] }) {
  return (
    <section className="rounded-xl border border-border-soft bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">Test Evidence Review</h3>
      <ul className="mt-3 grid gap-2 lg:grid-cols-2">
        {evidence.map((item) => (
          <li key={item.id} className="rounded-lg border border-border-soft bg-surface-2/50 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{item.label}</p>
                <p className="truncate font-mono text-[11px] text-ink-faint">
                  {item.command}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                  RESULT_STYLES[item.result],
                )}
              >
                {item.result}
              </span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
              {item.reason}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
