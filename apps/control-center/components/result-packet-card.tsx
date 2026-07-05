import { cn } from "@/lib/utils";
import type { PacketAgentName, PacketVerdict, ResultPacketView } from "@/lib/prompt-result-packet-types";

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

export function ResultPacketCard({ result }: { result: ResultPacketView }) {
  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            PACKET_AGENT_ACCENT[result.sourceAgent],
          )}
        >
          {result.sourceAgent}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            VERDICT_STYLES[result.verdict],
          )}
        >
          {result.verdict.replace(/_/g, " ")}
        </span>
        <span className="ml-auto font-mono text-[10px] text-ink-faint">{result.resultPacketId}</span>
      </div>

      <p className="mt-2 text-xs text-ink-muted">{result.summary}</p>

      {result.artifacts.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {result.artifacts.map((artifact) => (
            <span
              key={artifact.artifactId}
              className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border"
              title={artifact.summary}
            >
              {artifact.artifactType}
            </span>
          ))}
        </div>
      ) : null}

      {result.blockers.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {result.blockers.map((blocker) => (
            <li
              key={blocker}
              className="rounded bg-status-blocked/10 px-2 py-1 text-[11px] text-status-blocked"
            >
              {blocker}
            </li>
          ))}
        </ul>
      ) : null}

      {result.recommendedNextAgent ? (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-faint">
          recommended next:
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
              PACKET_AGENT_ACCENT[result.recommendedNextAgent],
            )}
          >
            {result.recommendedNextAgent}
          </span>
        </p>
      ) : null}
    </li>
  );
}
