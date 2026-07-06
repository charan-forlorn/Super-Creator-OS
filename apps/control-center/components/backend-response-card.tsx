import type { LocalBackendResponseView } from "@/lib/local-backend-types";

const STATUS_STYLES: Record<string, string> = {
  success: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  rejected: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  failure: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function BackendResponseCard({
  response,
}: {
  response: LocalBackendResponseView;
}) {
  const statusStyle = STATUS_STYLES[response.status] ?? STATUS_STYLES.failure;

  return (
    <div className="rounded-lg border border-border-soft bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-ink">{response.responseType}</p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${statusStyle}`}
        >
          {response.status}
        </span>
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-ink-muted">
        <dt className="text-ink-faint">request_id</dt>
        <dd className="truncate">{response.requestId}</dd>
        <dt className="text-ink-faint">request_type</dt>
        <dd className="truncate">{response.requestType}</dd>
        <dt className="text-ink-faint">schema_version</dt>
        <dd>{response.schemaVersion}</dd>
      </dl>

      {Object.keys(response.data).length > 0 ? (
        <div className="mt-2 rounded-md bg-surface-2 p-2">
          {Object.entries(response.data).map(([key, value]) => (
            <p key={key} className="text-[11px] text-ink-muted">
              <span className="text-ink-faint">{key}:</span> {value}
            </p>
          ))}
        </div>
      ) : null}

      {response.errors.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {response.errors.map((error, index) => (
            <li
              key={`${error.errorKind}-${index}`}
              className="rounded-md border border-status-blocked/30 bg-status-blocked/5 p-2 text-[11px] text-status-blocked"
            >
              <p className="font-semibold">{error.errorKind}</p>
              <p className="text-ink-muted">{error.errorDetail}</p>
              <p className="mt-0.5 text-ink-faint">recommended: {error.recommendedAction}</p>
            </li>
          ))}
        </ul>
      ) : null}

      {response.warnings.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {response.warnings.map((warning, index) => (
            <li
              key={`${warning.warningKind}-${index}`}
              className="rounded-md border border-status-review/30 bg-status-review/5 p-2 text-[11px] text-status-review"
            >
              <span className="font-semibold">{warning.warningKind}:</span>{" "}
              <span className="text-ink-muted">{warning.warningDetail}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
