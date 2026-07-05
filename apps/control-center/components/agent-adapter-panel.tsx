import type { AgentAdapterCardView } from "@/lib/agent-adapter-types";
import { AdapterContractCard } from "./adapter-contract-card";

export function AgentAdapterPanel({
  adapters,
}: {
  adapters: readonly AgentAdapterCardView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">AI Agent Adapters</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · real dispatch disabled
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Stage 5.3 adapter contract layer: one declared capability surface per
        agent, plus the always-on manual clipboard fallback. This panel only
        displays state produced by
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/agent_adapter_registry.py
        </code>
        — no adapter here calls an API, opens an app, or automates anything.
      </p>
      <ul className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {adapters.map((adapter) => (
          <AdapterContractCard key={adapter.adapterId} adapter={adapter} />
        ))}
      </ul>
    </section>
  );
}
