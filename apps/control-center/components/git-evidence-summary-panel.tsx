import type { GitEvidenceSnapshotView } from "@/lib/git-approval-types";

export function GitEvidenceSummaryPanel({
  snapshot,
}: {
  snapshot: GitEvidenceSnapshotView;
}) {
  const passedCount = snapshot.testEvidence.filter((item) => item.status === "passed").length;
  const failedCount = snapshot.testEvidence.filter((item) => item.status === "failed").length;

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Git Evidence Snapshot</h2>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
          {snapshot.snapshotId}
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Caller-supplied facts only — this snapshot never runs a git command
        itself; every field below was reported by the operator/upstream stage.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Branch</p>
          <p className="mt-1 font-mono text-xs text-ink">{snapshot.branch}</p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">HEAD</p>
          <p className="mt-1 truncate font-mono text-xs text-ink" title={snapshot.headCommit}>
            {snapshot.headCommit.slice(0, 12)}
          </p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            origin/main
          </p>
          <p
            className="mt-1 truncate font-mono text-xs text-ink"
            title={snapshot.originMainCommit}
          >
            {snapshot.originMainCommit.slice(0, 12)}
          </p>
        </div>
        <div className="rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Remote-only commits
          </p>
          <p className="mt-1 text-xs font-semibold text-ink">
            {snapshot.hasRemoteOnlyCommits ? "Yes — blocked" : "No"}
          </p>
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Changed files ({snapshot.changedFiles.length})
          </p>
          <ul className="mt-1 space-y-1">
            {snapshot.changedFiles.map((file) => (
              <li
                key={file.path}
                className="flex items-center justify-between gap-2 rounded bg-surface-2/40 px-2 py-1 text-[11px]"
              >
                <span className="truncate font-mono text-ink-muted" title={file.path}>
                  {file.path}
                </span>
                <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink-faint ring-1 ring-inset ring-border">
                  {file.changeType}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Test evidence ({passedCount} passed / {failedCount} failed)
          </p>
          <ul className="mt-1 space-y-1">
            {snapshot.testEvidence.map((evidence) => (
              <li
                key={evidence.evidenceId}
                className="rounded bg-surface-2/40 px-2 py-1 text-[11px] text-ink-muted"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{evidence.summary}</span>
                  <span
                    className={
                      evidence.status === "passed"
                        ? "shrink-0 rounded-full bg-status-approved/15 px-2 py-0.5 text-[10px] font-semibold text-status-approved ring-1 ring-inset ring-status-approved/30"
                        : "shrink-0 rounded-full bg-status-blocked/15 px-2 py-0.5 text-[10px] font-semibold text-status-blocked ring-1 ring-inset ring-status-blocked/30"
                    }
                  >
                    {evidence.status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-semibold">
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-ink-muted ring-1 ring-inset ring-border">
          {snapshot.isCleanBeforeStage ? "Working tree was clean" : "Working tree was dirty"}
        </span>
        {snapshot.riskFlags.length ? (
          snapshot.riskFlags.map((flag) => (
            <span
              key={flag}
              className="rounded-full bg-status-blocked/15 px-2 py-0.5 text-status-blocked ring-1 ring-inset ring-status-blocked/30"
            >
              {flag}
            </span>
          ))
        ) : (
          <span className="rounded-full bg-status-approved/15 px-2 py-0.5 text-status-approved ring-1 ring-inset ring-status-approved/30">
            no risk flags
          </span>
        )}
      </div>
    </section>
  );
}
