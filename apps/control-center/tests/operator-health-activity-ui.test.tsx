import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { OperatorHealthSignalCard } from "@/components/operator-health-signal-card";
import { OperatorActivityFeed } from "@/components/operator-activity-feed";
import { ReadSurfaceCoherenceCard } from "@/components/read-surface-coherence-card";
import { degradedOperatorReadSurfaceProjection } from "@/lib/operator-read-surface-mock-data";

describe("operator health/activity UI", () => {
  it("exposes degraded warnings in health signal cards", () => {
    const signal = degradedOperatorReadSurfaceProjection.healthSignals.find(
      (item) => item.signalType === "DRIFT",
    );
    expect(signal).toBeDefined();

    render(<OperatorHealthSignalCard signal={signal!} />);

    expect(screen.getByText("DRIFT")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(
      screen.getByText("Drift evidence is stale in this deterministic fixture."),
    ).toBeInTheDocument();
  });

  it("renders deterministic activity records with source stages", () => {
    render(
      <OperatorActivityFeed
        records={degradedOperatorReadSurfaceProjection.recentActivity.slice(0, 2)}
      />,
    );

    expect(screen.getByText("Recent Activity")).toBeInTheDocument();
    expect(screen.getByText(/Stage 7.4 UI projection in progress/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Stage 7.4/).length).toBeGreaterThan(0);
  });

  it("renders coherence warnings and fallback mode note", () => {
    render(
      <ReadSurfaceCoherenceCard
        coherence={degradedOperatorReadSurfaceProjection.coherence}
      />,
    );

    expect(screen.getByText("Read Surface Coherence")).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();
    expect(
      screen.getByText("Stage 7.5 live sync transport is pending approval."),
    ).toBeInTheDocument();
  });

  it("does not introduce forbidden live-transport tokens in Stage 7.4 files", () => {
    const sourcePaths = [
      "lib/operator-read-surface-types.ts",
      "lib/operator-read-surface-mock-data.ts",
      "lib/operator-read-surface-projection.ts",
      "components/operator-read-surface-panel.tsx",
      "components/operator-health-signal-card.tsx",
      "components/operator-activity-feed.tsx",
      "components/operator-readiness-summary.tsx",
      "components/read-surface-coherence-card.tsx",
    ];
    const combined = sourcePaths
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");
    const forbidden = [
      "fet" + "ch(",
      "XML" + "HttpRequest",
      "ax" + "ios",
      "Web" + "Socket",
      "Event" + "Source",
      "set" + "Interval",
      "set" + "Timeout",
      "Date." + "now",
      "new " + "Date(",
      "Math." + "random",
      "crypto." + "randomUUID",
      "route." + "ts",
      "middleware." + "ts",
    ];

    for (const token of forbidden) {
      expect(combined).not.toContain(token);
    }
  });
});
