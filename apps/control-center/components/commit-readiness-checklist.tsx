import { cn } from "@/lib/utils";
import type { CommitChecklistItem, CommitChecklistStatus } from "@/lib/types";

const CHECK_STYLES: Record<CommitChecklistStatus, string> = {
  pass: "bg-status-approved/20 text-status-approved ring-status-approved/40",
  fail: "bg-status-blocked/20 text-status-blocked ring-status-blocked/40",
  warning: "bg-status-working/20 text-status-working ring-status-working/40",
};

const CHECK_MARK: Record<CommitChecklistStatus, string> = {
  pass: "✓",
  fail: "!",
  warning: "?",
};

export function CommitReadinessChecklist({
  items,
}: {
  items: CommitChecklistItem[];
}) {
  return (
    <section className="rounded-xl border border-border-soft bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">Commit Readiness Checklist</h3>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li key={item.id} className="flex gap-2.5 rounded-lg bg-surface-2/40 p-2.5">
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-bold ring-1 ring-inset",
                CHECK_STYLES[item.status],
              )}
              aria-hidden
            >
              {CHECK_MARK[item.status]}
            </span>
            <span>
              <span className="block text-sm font-medium text-ink">{item.label}</span>
              <span className="block text-xs leading-relaxed text-ink-muted">
                {item.reason}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
