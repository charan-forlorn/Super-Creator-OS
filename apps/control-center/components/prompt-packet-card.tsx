import { cn } from "@/lib/utils";
import type { PacketAgentName, PromptPacketView } from "@/lib/prompt-result-packet-types";

const PACKET_AGENT_ACCENT: Record<PacketAgentName, string> = {
  chatgpt: "bg-status-working/15 text-status-working ring-status-working/30",
  claude_code: "bg-accent/15 text-accent ring-accent/30",
  codex: "bg-status-review/15 text-status-review ring-status-review/30",
  hermes: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  operator: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

const STATUS_STYLES: Record<string, string> = {
  drafted: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  ready_for_operator_review: "bg-status-review/15 text-status-review ring-status-review/30",
  approved_for_handoff: "bg-status-working/15 text-status-working ring-status-working/30",
  sent_to_agent: "bg-status-working/15 text-status-working ring-status-working/30",
  result_expected: "bg-status-working/15 text-status-working ring-status-working/30",
  cancelled: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function PromptPacketCard({ packet }: { packet: PromptPacketView }) {
  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            PACKET_AGENT_ACCENT[packet.sourceAgent],
          )}
        >
          {packet.sourceAgent}
        </span>
        <span className="text-ink-faint">&rarr;</span>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            PACKET_AGENT_ACCENT[packet.targetAgent],
          )}
        >
          {packet.targetAgent}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            STATUS_STYLES[packet.status] ?? STATUS_STYLES.drafted,
          )}
        >
          {packet.status.replace(/_/g, " ")}
        </span>
        <span className="ml-auto font-mono text-[10px] text-ink-faint">{packet.packetId}</span>
      </div>

      <p className="mt-2 text-xs font-semibold text-ink">{packet.title}</p>
      <p className="mt-1 text-[11px] text-ink-faint">
        {packet.packetType.replace(/_/g, " ")} &middot; {packet.createdAt}
      </p>
      <p className="mt-2 text-xs text-ink-muted">{packet.objective}</p>

      {packet.contextRefs.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {packet.contextRefs.map((ref) => (
            <span
              key={ref.refId}
              className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border"
              title={ref.summary}
            >
              {ref.refType}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}
