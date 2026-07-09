import { OperatorActivityFeed } from "./operator-activity-feed";
import { OperatorHealthSignalCard } from "./operator-health-signal-card";
import { OperatorReadinessSummary } from "./operator-readiness-summary";
import { ReadSurfaceCoherenceCard } from "./read-surface-coherence-card";
import type { OperatorReadSurfaceProjectionState } from "@/lib/operator-read-surface-types";

export function OperatorReadSurfacePanel({
  projection,
}: {
  projection: OperatorReadSurfaceProjectionState;
}) {
  if (projection.state === "loading") {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface p-5">
        <h3 className="text-sm font-semibold text-ink">
          Operator Read Surface
        </h3>
        <p className="mt-2 text-xs text-ink-muted">
          Loading deterministic operator projection fixture.
        </p>
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[11px] text-ink-faint">
          {projection.fallbackNotice}
        </p>
      </div>
    );
  }

  if (projection.state === "empty") {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface p-5">
        <h3 className="text-sm font-semibold text-ink">
          Operator Read Surface
        </h3>
        <p className="mt-2 text-xs text-ink-muted">
          No approved local operator projection is available in this fixture.
        </p>
        <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-[11px] text-ink-faint">
          {projection.fallbackNotice}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
        <p className="text-xs font-semibold text-status-review">
          Static/Mock Fallback
        </p>
        <p className="mt-1 text-[11px] text-ink-muted">
          {projection.fallbackNotice}
        </p>
      </div>

      <OperatorReadinessSummary summary={projection.readiness} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {projection.healthSignals.map((signal) => (
          <OperatorHealthSignalCard key={signal.signalId} signal={signal} />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_0.85fr]">
        <OperatorActivityFeed records={projection.recentActivity} />
        <ReadSurfaceCoherenceCard coherence={projection.coherence} />
      </div>
    </div>
  );
}
