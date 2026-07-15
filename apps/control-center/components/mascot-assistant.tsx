import { OrbitMascot as AnimatedOrbitMascot } from "@/components/cockpit/orbit-mascot";
import { cn } from "@/lib/utils";
import type { MascotMood } from "@/lib/types";
import type { MascotView } from "@/lib/utils";

const MOOD_STYLES: Record<MascotMood, { label: string; dot: string }> = {
  idle: { label: "Idle", dot: "bg-status-idle" },
  working: { label: "Working", dot: "bg-status-working" },
  blocked: { label: "Blocked", dot: "bg-status-blocked" },
  approved: { label: "All clear", dot: "bg-status-approved" },
  review: { label: "Thinking", dot: "bg-status-review" },
};

const MASCOT_STATE: Record<MascotMood, "normal" | "attention" | "success"> = {
  idle: "normal",
  working: "attention",
  blocked: "attention",
  approved: "success",
  review: "attention",
};

export function MascotAssistant({
  view,
  compact,
}: {
  view: MascotView;
  /** Visual density only; does not affect the workflow advice or task state. */
  compact?: boolean;
}) {
  const s = MOOD_STYLES[view.mood];
  return (
    <section
      aria-label="Orbit assistant"
      className={cn(
        "rounded-card border border-border bg-gradient-to-b from-surface-2 to-surface shadow-lg shadow-black/20",
        compact ? "p-4" : "p-5",
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-ink">Orbit</h2>
          <p className="text-xs text-ink-faint">Your control-center assistant</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-xs font-medium text-ink-muted ring-1 ring-inset ring-border">
          <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} aria-hidden />
          {s.label}
        </span>
      </div>

      <div className={cn("flex justify-center", compact ? "mt-1" : "mt-2")}>
        <AnimatedOrbitMascot state={MASCOT_STATE[view.mood]} size={compact ? 96 : 132} />
      </div>

      <p className="mt-1 text-center text-sm leading-relaxed text-ink">{view.message}</p>

      <div className={cn("space-y-3", compact ? "mt-3" : "mt-4")}>
        <div className="rounded-xl border border-border-soft bg-surface p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Recommended next action
          </p>
          <p className="mt-1 text-sm text-ink">{view.nextAction}</p>
        </div>
        <div className="rounded-xl border border-border-soft bg-surface p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Selected task
          </p>
          <p className="mt-1 text-sm text-ink-muted">{view.taskSummary}</p>
        </div>
      </div>
    </section>
  );
}
