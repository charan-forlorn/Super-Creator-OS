import { cn } from "@/lib/utils";
import type {
  AgentRuntimeView,
  AIWorkSessionView,
} from "@/lib/ai-work-session-types";

const AGENT_LABEL: Record<string, string> = {
  chatgpt: "ChatGPT",
  claude_code: "Claude Code",
  codex: "Codex",
  hermes: "Hermes",
};

function RuntimeCard({
  runtime,
  assignedCount,
}: {
  runtime: AgentRuntimeView;
  assignedCount: number;
}) {
  const isFallback = runtime.runtimeType === "manual_clipboard";
  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">{runtime.displayName}</span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border">
          {AGENT_LABEL[runtime.agentName] ?? runtime.agentName}
        </span>
        {isFallback ? (
          <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">
            always-on fallback
          </span>
        ) : null}
        <span
          className={cn(
            "ml-auto rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
            runtime.enabled
              ? "bg-status-approved/15 text-status-approved ring-status-approved/30"
              : "bg-status-idle/15 text-ink-faint ring-status-idle/25",
          )}
        >
          {runtime.enabled ? "enabled" : "disabled"}
        </span>
      </div>

      <p className="mt-1 font-mono text-[11px] text-ink-faint">{runtime.runtimeId}</p>

      <div className="mt-2 flex flex-wrap gap-1">
        {runtime.supportedTaskTypes.map((taskType) => (
          <span
            key={taskType}
            className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] text-ink-muted"
          >
            {taskType}
          </span>
        ))}
      </div>

      <p className="mt-2 text-[11px] text-ink-faint">
        {assignedCount} session{assignedCount === 1 ? "" : "s"} currently routed here
      </p>
    </li>
  );
}

export function AgentRoutingPanel({
  runtimes,
  sessions,
}: {
  runtimes: readonly AgentRuntimeView[];
  sessions: readonly AIWorkSessionView[];
}) {
  const assignedCounts = new Map<string, number>();
  for (const session of sessions) {
    if (!session.assignment) continue;
    const key = session.assignment.runtimeId;
    assignedCounts.set(key, (assignedCounts.get(key) ?? 0) + 1);
  }

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Agent Routing</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · registry is static
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Runtimes declared in
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/runtime_registry.py
        </code>
        . This panel only shows the catalogue and how sessions are currently
        routed — it never opens, calls, or drives any of these runtimes.
      </p>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {runtimes.map((runtime) => (
          <RuntimeCard
            key={runtime.runtimeId}
            runtime={runtime}
            assignedCount={assignedCounts.get(runtime.runtimeId) ?? 0}
          />
        ))}
      </ul>
    </section>
  );
}
