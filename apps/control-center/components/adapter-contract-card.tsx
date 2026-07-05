import { cn } from "@/lib/utils";
import type { AgentAdapterCardView } from "@/lib/agent-adapter-types";

const AGENT_ACCENT: Record<string, string> = {
  chatgpt: "bg-status-working/15 text-status-working ring-status-working/30",
  claude_code: "bg-accent/15 text-accent ring-accent/30",
  codex: "bg-status-review/15 text-status-review ring-status-review/30",
  hermes: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  manual_clipboard: "bg-status-idle/15 text-status-idle ring-status-idle/30",
};

function CapabilityFlag({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset",
        on
          ? "bg-status-approved/10 text-status-approved ring-status-approved/30"
          : "bg-surface-2 text-ink-faint ring-border",
      )}
    >
      {label}: {on ? "yes" : "no"}
    </span>
  );
}

export function AdapterContractCard({ adapter }: { adapter: AgentAdapterCardView }) {
  const runtimeTypes = adapter.capabilities.map((c) => c.runtimeType).join(", ");
  const taskTypes = Array.from(
    new Set(adapter.capabilities.flatMap((c) => c.taskTypes)),
  );
  const manualFallback = adapter.capabilities.some((c) => c.supportsManualFallback);

  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            AGENT_ACCENT[adapter.agentName] ?? AGENT_ACCENT.manual_clipboard,
          )}
        >
          {adapter.displayName}
        </span>
        {manualFallback ? (
          <span className="rounded-full bg-status-idle/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-status-idle ring-1 ring-inset ring-status-idle/30">
            always-on fallback
          </span>
        ) : null}
        <span className="ml-auto font-mono text-[10px] text-ink-faint">{adapter.adapterId}</span>
      </div>

      <p className="mt-2 text-xs text-ink-muted">{adapter.role}</p>
      <p className="mt-1 text-[11px] text-ink-faint">runtime types: {runtimeTypes}</p>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {taskTypes.map((taskType) => (
          <span
            key={taskType}
            className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border"
          >
            {taskType}
          </span>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <CapabilityFlag label="prompt delivery" on={adapter.capabilities.some((c) => c.supportsPromptDelivery)} />
        <CapabilityFlag label="result capture" on={adapter.capabilities.some((c) => c.supportsResultCapture)} />
        <CapabilityFlag label="status check" on={adapter.capabilities.some((c) => c.supportsStatusCheck)} />
        <CapabilityFlag label="manual fallback" on={manualFallback} />
      </div>
    </li>
  );
}
