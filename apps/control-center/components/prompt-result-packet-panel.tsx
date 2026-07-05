import type { PacketFlowStageView, PacketScenarioView } from "@/lib/prompt-result-packet-types";
import { PacketRoutingFlow } from "./packet-routing-flow";
import { PromptPacketCard } from "./prompt-packet-card";
import { ResultPacketCard } from "./result-packet-card";

export function PromptResultPacketPanel({
  scenarios,
  flow,
}: {
  scenarios: readonly PacketScenarioView[];
  flow: readonly PacketFlowStageView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Unified Prompt &amp; Result Packets</h2>
        <span className="text-[11px] text-ink-faint">mock data · no real AI dispatch</span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Stage 5.4 packet contract layer: a prompt packet handed to one agent,
        the result packet handed back, and (where applicable) a routing
        recommendation for what happens next. This panel only displays state
        shaped by
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/prompt_result_packet_builder.py
        </code>
        — nothing here sends a prompt, calls an API, or automates anything.
      </p>

      <ul className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {scenarios.map((scenario) => (
          <li key={scenario.scenarioId} className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
            <p className="mb-2 text-[11px] font-semibold text-ink-muted">{scenario.label}</p>
            <ul className="space-y-2">
              <PromptPacketCard packet={scenario.prompt} />
              <ResultPacketCard result={scenario.result} />
            </ul>
            {scenario.routing ? (
              <p className="mt-2 rounded bg-surface-2 px-2 py-1 text-[11px] text-ink-muted">
                routing: <span className="font-semibold">{scenario.routing.nextAgent}</span> /{" "}
                {scenario.routing.nextPacketType.replace(/_/g, " ")}
                {scenario.routing.requiresOperatorApproval ? " (operator approval required)" : ""}
              </p>
            ) : null}
          </li>
        ))}
      </ul>

      <div className="mt-4">
        <PacketRoutingFlow stages={flow} />
      </div>
    </section>
  );
}
