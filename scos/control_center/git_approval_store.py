"""SCOS Stage 5.8 local Git Approval JSONL store.

Append-only deterministic JSONL persistence for git evidence snapshots (via
the caller), commit proposals, commit approval decisions, push proposals,
push approval decisions, and the git approval event timeline. No SQLite, no
file locks, no background workers, no hidden paths, and no automatic
reads/writes to default locations — every instance is rooted at a
caller-supplied ``root_dir``.

This module never runs a git command, subprocess, or network call; it only
persists/reads the JSON produced by ``git_approval_models``/
``git_approval_builder``/``git_evidence_snapshot``.

Local-first, deterministic, stdlib-only. No clock, no random, no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .git_approval_models import (
        CommitApprovalDecision,
        CommitProposal,
        GitApprovalEvent,
        PushApprovalDecision,
        PushProposal,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from git_approval_models import (
        CommitApprovalDecision,
        CommitProposal,
        GitApprovalEvent,
        PushApprovalDecision,
        PushProposal,
    )

GIT_APPROVAL_STORE_SCHEMA_VERSION = 1

_EVENTS_FILE = "git_approval_events.jsonl"
_COMMIT_PROPOSALS_FILE = "git_commit_proposals.jsonl"
_COMMIT_DECISIONS_FILE = "git_commit_approval_decisions.jsonl"
_PUSH_PROPOSALS_FILE = "git_push_proposals.jsonl"
_PUSH_DECISIONS_FILE = "git_push_approval_decisions.jsonl"

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _ensure_local_root(root_dir: Any) -> Path:
    if isinstance(root_dir, str):
        text = root_dir.strip()
        if text.lower().startswith(_URL_PREFIXES) or _SCHEME_RE.match(text):
            raise ValueError("URL_PATH_REJECTED: root_dir must be a local path")
        return Path(text)
    if isinstance(root_dir, Path):
        return root_dir
    raise ValueError("INVALID_PATH: root_dir must be a str or pathlib.Path")


def _jsonl_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pairs_from_dict(value: Any) -> dict:
    if value is None:
        return {}
    return dict(value)


def _commit_proposal_from_dict(payload: dict) -> CommitProposal:
    return CommitProposal.of(
        payload.get("proposal_id", ""),
        payload.get("snapshot_id", ""),
        payload.get("task_id", ""),
        payload.get("session_id", ""),
        payload.get("commit_message", ""),
        payload.get("commit_title", ""),
        tuple(payload.get("files_to_commit", ())),
        payload.get("evidence_summary", ""),
        payload.get("test_summary", ""),
        payload.get("risk_level", "low"),
        payload.get("proposed_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        commit_body=payload.get("commit_body", ""),
        approval_required=bool(payload.get("approval_required", True)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _commit_decision_from_dict(payload: dict) -> CommitApprovalDecision:
    return CommitApprovalDecision.of(
        payload.get("decision_id", ""),
        payload.get("proposal_id", ""),
        payload.get("decision", ""),
        payload.get("decided_by", ""),
        payload.get("decided_at", ""),
        payload.get("reason", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        manual_command=payload.get("manual_command"),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _push_proposal_from_dict(payload: dict) -> PushProposal:
    return PushProposal.of(
        payload.get("push_proposal_id", ""),
        payload.get("commit_decision_id", ""),
        payload.get("push_snapshot_id", ""),
        payload.get("proposed_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        branch=payload.get("branch", "main"),
        remote=payload.get("remote", "origin"),
        refspec=payload.get("refspec", "main"),
        proposed_command=payload.get("proposed_command", "git push origin main"),
        risk_level=payload.get("risk_level", "low"),
        approval_required=bool(payload.get("approval_required", True)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _push_decision_from_dict(payload: dict) -> PushApprovalDecision:
    return PushApprovalDecision.of(
        payload.get("push_decision_id", ""),
        payload.get("push_proposal_id", ""),
        payload.get("decision", ""),
        payload.get("decided_by", ""),
        payload.get("decided_at", ""),
        payload.get("reason", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        manual_command=payload.get("manual_command"),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _event_from_dict(payload: dict) -> GitApprovalEvent:
    return GitApprovalEvent.of(
        payload.get("event_id", ""),
        payload.get("event_type", ""),
        payload.get("task_id", ""),
        payload.get("session_id", ""),
        payload.get("related_id", ""),
        payload.get("summary", ""),
        payload.get("created_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


class GitApprovalStore:
    """Append-only JSONL store rooted at ``root_dir``.

    Directories are created lazily on the first ``append_*`` call; the
    ``list_*`` methods never create anything and return an empty tuple when
    the backing file does not exist yet.
    """

    def __init__(self, path: Any) -> None:
        self._root_dir = _ensure_local_root(path)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def _path(self, filename: str) -> Path:
        return self._root_dir / filename

    def _append(self, filename: str, payload: dict) -> None:
        target = self._path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(_jsonl_line(payload) + "\n")

    def _read(self, filename: str, error_code: str) -> tuple[dict, ...]:
        target = self._path(filename)
        if not target.is_file():
            return ()
        objects: list[dict] = []
        text = target.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(
                    f"{error_code}: line {line_number} is not valid JSON"
                ) from None
            if not isinstance(payload, dict):
                raise ValueError(f"{error_code}: line {line_number} is not a JSON object")
            objects.append(payload)
        return tuple(objects)

    def append_event(self, event: GitApprovalEvent) -> None:
        if not isinstance(event, GitApprovalEvent):
            raise ValueError(
                "NOT_A_GIT_APPROVAL_EVENT: only GitApprovalEvent instances "
                "may be stored"
            )
        self._append(_EVENTS_FILE, event.to_dict())

    def append_commit_proposal(self, proposal: CommitProposal) -> None:
        if not isinstance(proposal, CommitProposal):
            raise ValueError(
                "NOT_A_COMMIT_PROPOSAL: only CommitProposal instances may "
                "be stored"
            )
        self._append(_COMMIT_PROPOSALS_FILE, proposal.to_dict())

    def append_commit_decision(self, decision: CommitApprovalDecision) -> None:
        if not isinstance(decision, CommitApprovalDecision):
            raise ValueError(
                "NOT_A_COMMIT_APPROVAL_DECISION: only CommitApprovalDecision "
                "instances may be stored"
            )
        self._append(_COMMIT_DECISIONS_FILE, decision.to_dict())

    def append_push_proposal(self, proposal: PushProposal) -> None:
        if not isinstance(proposal, PushProposal):
            raise ValueError(
                "NOT_A_PUSH_PROPOSAL: only PushProposal instances may be "
                "stored"
            )
        self._append(_PUSH_PROPOSALS_FILE, proposal.to_dict())

    def append_push_decision(self, decision: PushApprovalDecision) -> None:
        if not isinstance(decision, PushApprovalDecision):
            raise ValueError(
                "NOT_A_PUSH_APPROVAL_DECISION: only PushApprovalDecision "
                "instances may be stored"
            )
        self._append(_PUSH_DECISIONS_FILE, decision.to_dict())

    def list_events(self) -> tuple[GitApprovalEvent, ...]:
        payloads = self._read(_EVENTS_FILE, "INVALID_GIT_APPROVAL_EVENT_LINE")
        return tuple(_event_from_dict(payload) for payload in payloads)

    def list_commit_proposals(self) -> tuple[CommitProposal, ...]:
        payloads = self._read(_COMMIT_PROPOSALS_FILE, "INVALID_COMMIT_PROPOSAL_LINE")
        return tuple(_commit_proposal_from_dict(payload) for payload in payloads)

    def list_commit_decisions(self) -> tuple[CommitApprovalDecision, ...]:
        payloads = self._read(_COMMIT_DECISIONS_FILE, "INVALID_COMMIT_DECISION_LINE")
        return tuple(_commit_decision_from_dict(payload) for payload in payloads)

    def list_push_proposals(self) -> tuple[PushProposal, ...]:
        payloads = self._read(_PUSH_PROPOSALS_FILE, "INVALID_PUSH_PROPOSAL_LINE")
        return tuple(_push_proposal_from_dict(payload) for payload in payloads)

    def list_push_decisions(self) -> tuple[PushApprovalDecision, ...]:
        payloads = self._read(_PUSH_DECISIONS_FILE, "INVALID_PUSH_DECISION_LINE")
        return tuple(_push_decision_from_dict(payload) for payload in payloads)
