import { cn } from "@/lib/utils";
import type { ChangedFileReview, ChangedFileScopeStatus } from "@/lib/types";

const SCOPE_STYLES: Record<ChangedFileScopeStatus, string> = {
  allowed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  warning: "bg-status-working/15 text-status-working ring-status-working/30",
  forbidden: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function ChangedFilesReview({ files }: { files: ChangedFileReview[] }) {
  const counts = files.reduce(
    (acc, file) => ({ ...acc, [file.scopeStatus]: acc[file.scopeStatus] + 1 }),
    { allowed: 0, warning: 0, forbidden: 0 },
  );

  return (
    <section className="rounded-xl border border-border-soft bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Changed Files Scope Review</h3>
        <div className="flex gap-2 text-[11px]">
          <span className="text-status-approved">{counts.allowed} allowed</span>
          <span className="text-status-working">{counts.warning} warning</span>
          <span className="text-status-blocked">{counts.forbidden} forbidden</span>
        </div>
      </div>

      <ul className="mt-3 space-y-2">
        {files.map((file) => (
          <li key={file.id} className="rounded-lg border border-border-soft bg-surface-2/50 p-3">
            <div className="flex flex-wrap items-start gap-2">
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                  SCOPE_STYLES[file.scopeStatus],
                )}
              >
                {file.scopeStatus}
              </span>
              <span className="font-mono text-xs text-ink">{file.filePath}</span>
              <span className="ml-auto rounded-full bg-surface px-2 py-0.5 text-[10px] text-ink-faint ring-1 ring-inset ring-border">
                {file.changeType}
              </span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
              {file.reason}
            </p>
            <p className="mt-1 text-[11px] text-ink-faint">
              Owning area: {file.owningArea}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
