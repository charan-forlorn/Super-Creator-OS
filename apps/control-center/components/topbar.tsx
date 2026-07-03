import { cn } from "@/lib/utils";
import type { Agent, StageProgress } from "@/lib/types";

const ACCENT_TEXT: Record<Agent["accent"], string> = {
  emerald: "text-agent-emerald",
  violet: "text-agent-violet",
  sky: "text-agent-sky",
  amber: "text-agent-amber",
};

const ACCENT_DOT: Record<Agent["accent"], string> = {
  emerald: "bg-agent-emerald",
  violet: "bg-agent-violet",
  sky: "bg-agent-sky",
  amber: "bg-agent-amber",
};

export function Topbar({
  stage,
  activeAgent,
}: {
  stage: StageProgress;
  activeAgent: Agent | undefined;
}) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-surface/40 px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">
          Agent Control Center
        </h1>
        <p className="text-xs text-ink-faint">
          Coordinate ChatGPT, Claude Code, Codex &amp; Hermes across SCOS stages.
        </p>
      </div>

      <div className="flex items-center gap-3">
        {/* Current stage */}
        <div className="hidden items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 sm:flex">
          <span className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
            Stage
          </span>
          <span className="text-sm font-semibold text-ink">
            {stage.currentStageLabel}
          </span>
          <span className="text-xs text-ink-faint">
            · {stage.percentComplete}%
          </span>
        </div>

        {/* Active agent */}
        {activeAgent ? (
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5">
            <span
              className={cn(
                "h-2 w-2 animate-pulse rounded-full",
                ACCENT_DOT[activeAgent.accent],
              )}
              aria-hidden
            />
            <span className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">
              Active
            </span>
            <span
              className={cn(
                "text-sm font-semibold",
                ACCENT_TEXT[activeAgent.accent],
              )}
            >
              {activeAgent.name}
            </span>
          </div>
        ) : null}
      </div>
    </header>
  );
}
