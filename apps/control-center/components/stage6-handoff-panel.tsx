import type {
  HandoffPriority,
  Stage6HandoffItemView,
} from "@/lib/stage5-certification-types";

const PRIORITY_STYLES: Record<HandoffPriority, string> = {
  low: "bg-surface-2 text-ink-faint ring-border",
  normal: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  high: "bg-status-review/15 text-status-review ring-status-review/30",
  urgent: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function Stage6HandoffPanel({
  items,
}: {
  items: readonly Stage6HandoffItemView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">Stage 6 Handoff Plan</h3>
        <span className="text-[11px] text-ink-faint">{items.length} items</span>
      </div>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li
            key={item.itemId}
            className="rounded-lg border border-border-soft bg-surface-2/40 p-2.5"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-ink">{item.title}</p>
                <p className="mt-0.5 text-[11px] text-ink-muted">{item.description}</p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${PRIORITY_STYLES[item.priority]}`}
              >
                {item.priority}
              </span>
            </div>
            <p className="mt-1.5 text-[10px] text-ink-faint">
              {item.itemId} · {item.category} · owner {item.stage6Owner}
              {item.sourceStage5Evidence ? ` · evidence ${item.sourceStage5Evidence}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
