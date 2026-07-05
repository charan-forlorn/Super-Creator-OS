import { cn } from "@/lib/utils";
import type {
  AgentAdapterRequestView,
  AgentAdapterSimulationEventView,
} from "@/lib/agent-adapter-types";

const EVENT_LABEL: Record<string, string> = {
  request_created: "Request created",
  request_validated: "Request validated",
  adapter_selected: "Adapter selected",
  prompt_prepared: "Prompt prepared",
  manual_clipboard_ready: "Manual clipboard ready",
  simulated_sent: "Simulated send",
  result_simulated: "Result simulated",
  result_ready: "Result ready",
  blocked: "Blocked",
};

const STATUS_STYLES: Record<string, string> = {
  accepted: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  prepared: "bg-status-working/15 text-status-working ring-status-working/30",
  simulated_sent: "bg-status-working/15 text-status-working ring-status-working/30",
  waiting_for_operator: "bg-status-review/15 text-status-review ring-status-review/30",
  result_ready: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  failed: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function AdapterSimulationPanel({
  request,
  events,
}: {
  request: AgentAdapterRequestView;
  events: readonly AgentAdapterSimulationEventView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Simulated Adapter Lifecycle</h2>
        <span className="text-[11px] text-ink-faint">mock data · no AI execution</span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        One deterministic lifecycle for a {request.taskType} request routed to{" "}
        {request.agentName}, mirroring
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          simulate_adapter_lifecycle()
        </code>
        in
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/agent_adapter_simulator.py
        </code>
        . Real dispatch is disabled — every step below is simulated, local state.
      </p>

      <ol className="mt-3 space-y-2">
        {events.map((event, index) => (
          <li
            key={event.eventId}
            className="flex items-center gap-3 rounded-lg border border-border-soft bg-surface/70 px-3 py-2"
          >
            <span className="font-mono text-[10px] text-ink-faint">{index + 1}</span>
            <span className="flex-1 text-xs text-ink">
              {EVENT_LABEL[event.eventType] ?? event.eventType}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
                STATUS_STYLES[event.statusAfter] ?? STATUS_STYLES.accepted,
              )}
            >
              {event.statusAfter.replace(/_/g, " ")}
            </span>
          </li>
        ))}
      </ol>

      <p className="mt-3 rounded bg-surface-2 px-2.5 py-1.5 text-[11px] text-ink-muted">
        Next: Stage 5.4 — Unified Prompt &amp; Result Packet will define a
        shared packet format and attach adapter results back onto a Stage
        5.2 work session.
      </p>
    </section>
  );
}
