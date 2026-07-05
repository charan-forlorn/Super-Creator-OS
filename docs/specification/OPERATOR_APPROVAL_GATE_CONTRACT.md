# Operator Approval Gate Contract (Stage 5.1)

## Purpose

Define the mandatory human gate between a validated command draft and anything
executable. In Stage 5.1 no command reaches the queue or the runner without an
explicit operator decision recorded as an `OperatorApproval`.

## Approval schema

`OperatorApproval` (immutable dataclass, `to_dict()` keys in this order):

```json
{"approval_id": "apr-<sha256-16>",
 "command_id": "cmd-001",
 "approved": true,
 "approved_by": "operator-a",
 "approved_at": "2026-07-05T10:05:00Z",
 "reason": "checks reviewed",
 "metadata": []}
```

- `approval_id` is deterministic:
  `"apr-" + sha256(command_id | approved_by | approved_at | decision)[:16]`
  where `decision` is `"approved"` or `"rejected"`. No clock, no random, no
  uuid; `approved_at` is always supplied explicitly by the caller.
- One approval record covers exactly one `command_id`.

## Approval lifecycle

```
CommandDraft --validate--> (valid)   --approve_command--> OperatorApproval(approved=true)
                       \-> (any)     --reject_command---> OperatorApproval(approved=false)

CommandDraft + granting OperatorApproval --create_approved_command--> ApprovedCommand
```

Only an `ApprovedCommand` may be queued (`append_approved_command`) or run
(`run_approved_command`).

## Reject vs approve behavior

- `approve_command(draft=..., approved_by=..., approved_at=..., reason=...)`
  validates the draft first and raises the stable
  `ValueError("INVALID_DRAFT: ...")` when validation fails — an invalid draft
  can never be approved.
- `reject_command(draft=..., rejected_by=..., rejected_at=..., reason=...)`
  records `approved=false` and works for ANY draft, valid or not (operators
  can always say no).
- `create_approved_command(draft=..., approval=...)` returns an
  `ApprovedCommand` on success, or `(None, error)` with a stable message when:
  - `approval.approved` is false → `APPROVAL_NOT_GRANTED: ...`
  - `approval.command_id != draft.command_id` → `COMMAND_ID_MISMATCH: ...`
  - the draft fails validation → `INVALID_DRAFT: ...`

## Human / operator responsibility

The approval decision is a human act. The operator who sets `approved_by` is
accountable for having reviewed the draft's command type, args, and summary
against the allowlist and forbidden-text rules. `reason` must record why the
decision was made; it is preserved verbatim in the approval record.

## No auto-approval

There is no code path that produces `approved=true` without an explicit
`approve_command` call carrying an operator identity and timestamp. Nothing
in the bridge schedules, defaults, or infers approval; there is no batch or
implicit approval, and validation success alone approves nothing.

## No command execution without approval

`run_approved_command` accepts only `ApprovedCommand` instances and raises the
stable `NOT_AN_APPROVED_COMMAND` error for anything else (including raw
drafts). Since `ApprovedCommand` is only produced by
`create_approved_command` under the guards above, execution is impossible
without a granting, matching, operator-issued approval.
