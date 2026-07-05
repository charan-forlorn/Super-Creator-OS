import { cn } from "@/lib/utils";
import type { CommandDraftView, CommandValidationVerdict } from "@/lib/command-types";

const VERDICT_STYLES: Record<CommandValidationVerdict, string> = {
  valid: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  invalid: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

function DraftCard({ draft }: { draft: CommandDraftView }) {
  return (
    <article className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-faint">{draft.commandId}</span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border">
          {draft.commandType}
        </span>
        <span
          className={cn(
            "ml-auto rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
            VERDICT_STYLES[draft.validation.verdict],
          )}
        >
          {draft.validation.verdict === "valid" ? "VALIDATED" : "VALIDATION FAILED"}
        </span>
      </div>

      <p className="mt-2 text-sm text-ink">{draft.summary}</p>
      <p className="mt-1 text-[11px] text-ink-faint">
        Requested by {draft.requestedBy} · {draft.createdAt}
      </p>

      {draft.args.length > 0 ? (
        <dl className="mt-2 space-y-1">
          {draft.args.map(([key, value]) => (
            <div key={key} className="flex gap-2 font-mono text-[11px]">
              <dt className="text-ink-faint">{key}:</dt>
              <dd className="text-ink-muted">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {draft.validation.errors.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {draft.validation.errors.map((error) => (
            <li
              key={error}
              className="rounded bg-status-blocked/10 px-2 py-1 font-mono text-[11px] text-status-blocked"
            >
              {error}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[11px] text-status-approved">
          0 validation errors · approval required before queueing
        </p>
      )}
    </article>
  );
}

export function CommandDraftPanel({ drafts }: { drafts: readonly CommandDraftView[] }) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Command Drafts</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · no real execution
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Stage 5.1 local command bridge: draft → validate → operator approval →
        JSONL queue → allowlisted runner → event log.
      </p>
      <div className="mt-3 space-y-3">
        {drafts.map((draft) => (
          <DraftCard key={draft.commandId} draft={draft} />
        ))}
      </div>
    </section>
  );
}
