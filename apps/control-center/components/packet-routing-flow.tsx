import { cn } from "@/lib/utils";
import type { PacketAgentName, PacketFlowStageView, PacketVerdict } from "@/lib/prompt-result-packet-types";

const PACKET_AGENT_ACCENT: Record<PacketAgentName, string> = {
  chatgpt: "bg-status-working/15 text-status-working ring-status-working/30",
  claude_code: "bg-accent/15 text-accent ring-accent/30",
  codex: "bg-status-review/15 text-status-review ring-status-review/30",
  hermes: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  operator: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

const VERDICT_STYLES: Record<PacketVerdict, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  PASS_WITH_WARNINGS: "bg-status-review/15 text-status-review ring-status-review/30",
  NEEDS_FIX: "bg-status-review/15 text-status-review ring-status-review/30",
  BLOCKED: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  INFO: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

export function PacketRoutingFlow({ stages }: { stages: readonly PacketFlowStageView[] }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">5-Stage Routing Flow</h3>
        <span className="text-[11px] text-ink-faint">mock data · recommendation only</span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Mirrors the recommendation table in
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/prompt_result_packet_builder.py
        </code>
        . Nothing here dispatches a prompt or executes a routing decision.
      </p>

      <ol className="mt-3 flex flex-wrap items-center gap-2">
        {stages.map((stage, index) => (
          <li key={stage.stageLabel} className="flex items-center gap-2">
            <div className="flex flex-col items-center gap-1 rounded-lg border border-border-soft bg-surface/70 px-3 py-2">
              <span className="text-[10px] text-ink-faint">{stage.stageLabel}</span>
              <span
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
                  PACKET_AGENT_ACCENT[stage.agent],
                )}
              >
                {stage.agent}
              </span>
              <span className="text-[10px] text-ink-muted">{stage.packetType.replace(/_/g, " ")}</span>
              {stage.resultVerdict ? (
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase ring-1 ring-inset",
                    VERDICT_STYLES[stage.resultVerdict],
                  )}
                >
                  {stage.resultVerdict.replace(/_/g, " ")}
                </span>
              ) : null}
            </div>
            {index < stages.length - 1 ? <span className="text-ink-faint">&rarr;</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
