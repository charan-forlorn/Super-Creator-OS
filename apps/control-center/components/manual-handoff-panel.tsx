import type { OperatorPacketReviewView } from "@/lib/operator-packet-review-types";

export function ManualHandoffPanel({ review }: { review: OperatorPacketReviewView }) {
  const handoff = review.handoffPreview;

  return (
    <section className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold text-ink">Manual Handoff Package</h3>
          <p className="mt-1 text-[11px] text-ink-faint">
            Local-only preview. No clipboard button, no app launch, no dispatch.
          </p>
        </div>
        <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent ring-1 ring-inset ring-accent/30">
          copy manually outside SCOS
        </span>
      </div>

      {handoff ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="rounded bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Target
            </p>
            <p className="mt-1 text-xs text-ink">
              {handoff.targetAgent} / {handoff.targetRuntimeId}
            </p>
            <p className="mt-1 font-mono text-[10px] text-ink-faint">
              {handoff.handoffId}
            </p>
            <p className="mt-2 text-[11px] text-ink-muted">{handoff.manifestPath}</p>
          </div>

          <div className="rounded bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Operator Steps
            </p>
            <ol className="mt-2 space-y-1 text-[11px] text-ink-muted">
              {handoff.steps.map((step, index) => (
                <li key={step}>
                  {index + 1}. {step}
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Prompt Preview
            </p>
            <p className="mt-2 text-xs leading-relaxed text-ink-muted">
              {handoff.promptPreview}
            </p>
          </div>

          <div className="rounded bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Context Summary
            </p>
            <p className="mt-2 text-xs leading-relaxed text-ink-muted">
              {handoff.contextSummaryPreview}
            </p>
          </div>
        </div>
      ) : (
        <p className="mt-3 rounded bg-surface px-3 py-2 text-xs text-ink-muted">
          No handoff package is prepared for this packet yet. Choosing Prepare
          Manual Handoff only updates this mock state; it does not write files
          from the frontend.
        </p>
      )}
    </section>
  );
}
