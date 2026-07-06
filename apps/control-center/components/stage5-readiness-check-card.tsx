import type {
  CertificationSeverity,
  CertificationCheckStatus,
  Stage5CertificationCheckView,
} from "@/lib/stage5-certification-types";

const STATUS_STYLES: Record<CertificationCheckStatus, string> = {
  success: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  failure: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  skipped: "bg-surface-2 text-ink-faint ring-border",
};

const SEVERITY_STYLES: Record<CertificationSeverity, string> = {
  info: "text-ink-faint",
  warning: "text-status-review",
  error: "text-status-blocked",
  critical: "text-status-blocked",
};

export function Stage5ReadinessCheckCard({
  check,
}: {
  check: Stage5CertificationCheckView;
}) {
  return (
    <div className="flex items-start justify-between gap-2 rounded-lg border border-border-soft bg-surface-2/40 p-2.5">
      <div className="min-w-0">
        <p className="truncate font-mono text-[11px] text-ink">{check.checkName}</p>
        <p className="mt-0.5 truncate text-[10px] text-ink-faint">{check.category}</p>
        {check.errorDetail ? (
          <p className={`mt-1 text-[10px] ${SEVERITY_STYLES[check.severity]}`}>
            {check.errorDetail}
          </p>
        ) : null}
      </div>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${STATUS_STYLES[check.status]}`}
      >
        {check.status}
      </span>
    </div>
  );
}
