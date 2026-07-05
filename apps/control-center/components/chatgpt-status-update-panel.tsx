import type { ChatGPTStatusUpdatePacketView } from "@/lib/result-intake-types";

const ACTION_LABEL: Record<ChatGPTStatusUpdatePacketView["requestedChatGPTAction"], string> = {
  summarize_status: "Summarize status",
  decide_next_action: "Decide next action",
  update_stage_plan: "Update stage plan",
  prepare_review_prompt: "Prepare review prompt",
  prepare_fix_prompt: "Prepare fix prompt",
  prepare_commit_recommendation: "Prepare commit recommendation",
  mark_blocked: "Mark blocked",
  request_operator_decision: "Request operator decision",
};

export function ChatGPTStatusUpdatePanel({
  packet,
}: {
  packet: ChatGPTStatusUpdatePacketView;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">ChatGPT Status Update</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Manual-handoff packet. Nothing here is sent to ChatGPT automatically — copy the
            text below yourself.
          </p>
        </div>
        <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent ring-1 ring-inset ring-accent/30">
          {ACTION_LABEL[packet.requestedChatGPTAction]}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-semibold">
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-ink-faint ring-1 ring-inset ring-border">
          {packet.updatePacketId}
        </span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-ink-muted ring-1 ring-inset ring-border">
          {packet.sessionId} / {packet.taskId}
        </span>
        <span className="rounded-full bg-status-approved/15 px-2 py-0.5 text-status-approved ring-1 ring-inset ring-status-approved/30">
          {packet.resultVerdict}
        </span>
      </div>

      <p className="mt-3 text-xs text-ink-muted">{packet.resultSummary}</p>

      <div className="mt-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
          Status update body (manual handoff text)
        </p>
        <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-border-soft bg-surface-2/50 p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
{packet.statusUpdateBody}
        </pre>
      </div>

      {packet.evidenceRefs.length ? (
        <div className="mt-3 rounded bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Evidence references
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted">
            {packet.evidenceRefs.map((ref) => (
              <li key={ref}>{ref}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div
        aria-disabled
        className="mt-3 flex items-center justify-between rounded-lg border border-dashed border-border-soft bg-surface-2/30 px-3 py-2 text-[11px] text-ink-faint"
      >
        <span>Copy this text into ChatGPT manually. This button is inert — no clipboard access.</span>
        <button
          type="button"
          disabled
          className="cursor-not-allowed rounded-full border border-border-soft px-3 py-1 text-[10px] font-semibold text-ink-faint opacity-60"
        >
          Copy (disabled)
        </button>
      </div>
    </section>
  );
}
