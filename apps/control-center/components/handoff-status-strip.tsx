import { cn } from "@/lib/utils";
import type { HandoffStep, WorkflowState } from "@/lib/types";

const STATE_STYLES: Record<WorkflowState, string> = {
  ready: "bg-agent-sky/15 text-agent-sky ring-agent-sky/30",
  working: "bg-status-working/15 text-status-working ring-status-working/30",
  waiting_result: "bg-surface-2 text-ink-muted ring-border",
  needs_review: "bg-status-review/15 text-status-review ring-status-review/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
};

const STATE_LABEL: Record<WorkflowState, string> = {
  ready: "Ready",
  working: "Working",
  waiting_result: "Waiting result",
  needs_review: "Needs review",
  blocked: "Blocked",
  approved: "Approved",
};

export function HandoffStatusStrip({ steps }: { steps: HandoffStep[] }) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Handoff</h2>
        <span className="text-[11px] text-ink-faint">
          ChatGPT to Claude Code to Codex to Hermes to Merge Decision
        </span>
      </div>

      <ol className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className="relative rounded-xl border border-border-soft bg-surface-2/50 p-3"
          >
            {index < steps.length - 1 ? (
              <span
                aria-hidden
                className="absolute -right-2 top-1/2 hidden h-px w-4 bg-border xl:block"
              />
            ) : null}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">
                  {step.name}
                </p>
                <p className="text-[11px] text-ink-faint">{step.role}</p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                  STATE_STYLES[step.state],
                )}
              >
                {STATE_LABEL[step.state]}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-ink-muted">
              {step.message}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
