import type {
  DurableApprovalRecordView,
  DurableCommandRecordView,
} from "@/lib/durable-state-types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[10px] uppercase tracking-wide text-ink-faint">
        {label}
      </span>
      <span className="text-xs text-ink">{value}</span>
    </div>
  );
}

export function CommandRecordCard({
  record,
}: {
  record: DurableCommandRecordView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-ink">Command Record</h4>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          {record.status}
        </span>
      </div>
      <div className="mt-2 space-y-1.5">
        <Field label="command_id" value={record.commandId} />
        <Field label="command_type" value={record.commandType} />
        <Field label="request_id" value={record.requestId ?? "-"} />
        <Field label="session_id" value={record.sessionId ?? "-"} />
        <Field label="created_at" value={record.createdAt} />
        <Field label="updated_at" value={record.updatedAt ?? "-"} />
      </div>
    </div>
  );
}

export function ApprovalRecordCard({
  record,
}: {
  record: DurableApprovalRecordView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-ink">Approval Record</h4>
        <span className="rounded-full bg-status-approved/15 px-2 py-0.5 text-[10px] font-medium text-status-approved">
          {record.decision}
        </span>
      </div>
      <div className="mt-2 space-y-1.5">
        <Field label="approval_id" value={record.approvalId} />
        <Field label="approval_type" value={record.approvalType} />
        <Field label="subject" value={`${record.subjectType}:${record.subjectId}`} />
        <Field label="decided_by" value={record.decidedBy} />
        <Field label="decided_at" value={record.decidedAt} />
        <Field label="reason" value={record.reason ?? "-"} />
      </div>
    </div>
  );
}
