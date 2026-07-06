import type {
  GoNoGo,
  Stage5FinalCertificationResultView,
} from "@/lib/stage5-certification-types";
import { Stage5ReadinessCheckCard } from "./stage5-readiness-check-card";
import { Stage6HandoffPanel } from "./stage6-handoff-panel";

const VERDICT_STYLES: Record<GoNoGo, string> = {
  GO: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  NO_GO: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

function BoundaryBanner() {
  return (
    <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
      <p className="text-xs font-semibold text-status-review">
        This is a static, read-only certification mirror.
      </p>
      <ul className="mt-1 space-y-0.5 text-[11px] text-ink-muted">
        <li>• SCOS does not dispatch AI work, call a network, or automate a browser/GUI/clipboard here.</li>
        <li>• This panel never fixes a finding; it only reports what the gate found.</li>
        <li>• Real contracts live in scos/control_center/stage5_final_certification.py.</li>
      </ul>
    </div>
  );
}

function VerdictBanner({
  result,
}: {
  result: Stage5FinalCertificationResultView;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
          Stage 5 Final Certification
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          readiness {result.readinessScore}/{result.readinessMaxScore} · {result.readinessLevel}
        </p>
      </div>
      <span
        className={`rounded-full px-3 py-1 text-sm font-semibold ring-1 ring-inset ${VERDICT_STYLES[result.goNoGo]}`}
      >
        {result.goNoGo}
      </span>
    </div>
  );
}

export function Stage5CertificationPanel({
  result,
}: {
  result: Stage5FinalCertificationResultView;
}) {
  const failing = result.checks.filter((c) => c.status !== "success");
  const passing = result.checks.filter((c) => c.status === "success");

  return (
    <div className="space-y-3">
      <BoundaryBanner />
      <VerdictBanner result={result} />

      {result.blockers.length > 0 ? (
        <section className="rounded-card border border-status-blocked/30 bg-status-blocked/5 p-4">
          <h3 className="text-sm font-semibold text-status-blocked">
            Blockers ({result.blockers.length})
          </h3>
          <ul className="mt-2 space-y-2">
            {result.blockers.map((b) => (
              <li key={b.blockerId} className="rounded-lg border border-border-soft bg-surface p-2.5">
                <p className="text-xs font-semibold text-ink">{b.title}</p>
                <p className="mt-0.5 text-[11px] text-ink-muted">{b.detail}</p>
                <p className="mt-1 text-[10px] text-ink-faint">
                  {b.blockerId} · {b.severity} · recommended: {b.recommendedAction}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-card border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-ink">
          Stage 5.1-5.9 check matrix ({passing.length}/{result.checks.length} passing)
        </h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {failing.map((c) => (
            <Stage5ReadinessCheckCard key={c.checkName} check={c} />
          ))}
          {passing.map((c) => (
            <Stage5ReadinessCheckCard key={c.checkName} check={c} />
          ))}
        </div>
      </section>

      <Stage6HandoffPanel items={result.stage6HandoffItems} />
    </div>
  );
}
