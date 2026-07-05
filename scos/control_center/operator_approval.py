"""SCOS Stage 5.1 Control Center operator approval gate.

A command draft can only become an ``ApprovedCommand`` through an explicit
human operator decision recorded here. There is no auto-approval path:
``approve_command`` refuses invalid drafts, and ``create_approved_command``
refuses non-approving or mismatched approvals.

Approval ids are content-derived (SHA-256 over command_id + approver +
timestamp + decision flag), so identical decisions always produce identical
ids.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib

try:
    from .command_models import ApprovedCommand, CommandDraft, OperatorApproval
    from .command_validation import validate_command_draft
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_models import ApprovedCommand, CommandDraft, OperatorApproval
    from command_validation import validate_command_draft

CONTROL_CENTER_OPERATOR_APPROVAL_SCHEMA_VERSION = 1

_APPROVAL_ID_DIGEST_LENGTH = 16


def _approval_id(
    command_id: str,
    approved_by: str,
    approved_at: str,
    approved: bool,
) -> str:
    decision = "approved" if approved else "rejected"
    digest = hashlib.sha256(
        "|".join((command_id, approved_by, approved_at, decision)).encode("utf-8")
    ).hexdigest()[:_APPROVAL_ID_DIGEST_LENGTH]
    return f"apr-{digest}"


def approve_command(
    *,
    draft: CommandDraft,
    approved_by: str,
    approved_at: str,
    reason: str,
) -> OperatorApproval:
    """Record an explicit operator approval for a VALID draft.

    Raises ``ValueError`` with a stable ``INVALID_DRAFT`` message when the
    draft fails validation — an invalid draft can never be approved.
    ``approved_at`` must be supplied explicitly (no clock is read).
    """
    ok, errors = validate_command_draft(draft)
    if not ok:
        raise ValueError(f"INVALID_DRAFT: {'; '.join(errors)}")
    return OperatorApproval.of(
        approval_id=_approval_id(draft.command_id, approved_by, approved_at, True),
        command_id=draft.command_id,
        approved=True,
        approved_by=approved_by,
        approved_at=approved_at,
        reason=reason,
    )


def reject_command(
    *,
    draft: CommandDraft,
    rejected_by: str,
    rejected_at: str,
    reason: str,
) -> OperatorApproval:
    """Record an explicit operator rejection. Works for any draft, valid or not."""
    return OperatorApproval.of(
        approval_id=_approval_id(draft.command_id, rejected_by, rejected_at, False),
        command_id=draft.command_id,
        approved=False,
        approved_by=rejected_by,
        approved_at=rejected_at,
        reason=reason,
    )


def create_approved_command(
    *,
    draft: CommandDraft,
    approval: OperatorApproval,
) -> ApprovedCommand | tuple[None, str]:
    """Bind a draft to a granting approval, producing an ``ApprovedCommand``.

    Returns ``(None, error)`` with a stable message when the approval does not
    grant execution, targets a different command, or the draft is invalid.
    """
    if not approval.approved:
        return None, (
            f"APPROVAL_NOT_GRANTED: approval {approval.approval_id} "
            f"rejected command {approval.command_id}"
        )
    if approval.command_id != draft.command_id:
        return None, (
            f"COMMAND_ID_MISMATCH: approval targets {approval.command_id!r}, "
            f"draft is {draft.command_id!r}"
        )
    ok, errors = validate_command_draft(draft)
    if not ok:
        return None, f"INVALID_DRAFT: {'; '.join(errors)}"
    return ApprovedCommand.of(
        command_id=draft.command_id,
        command_type=draft.command_type,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        args=draft.args,
        metadata=draft.metadata,
    )
