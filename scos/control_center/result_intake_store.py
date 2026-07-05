"""SCOS Stage 5.7 local Result Intake JSONL store.

Append-only deterministic JSONL persistence for AI result intake records,
ChatGPT status update packets, project state updates, and next action
decisions. No SQLite, no file locks, no background workers, no hidden paths,
and no automatic reads/writes to default locations — every instance is
rooted at a caller-supplied ``root_dir``.

Local-first, deterministic, stdlib-only. No clock, no random, no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .result_intake_models import (
        AIResultIntakeRecord,
        ChatGPTStatusUpdatePacket,
        NextActionDecision,
        ProjectStateUpdate,
        ResultIntakeArtifact,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from result_intake_models import (
        AIResultIntakeRecord,
        ChatGPTStatusUpdatePacket,
        NextActionDecision,
        ProjectStateUpdate,
        ResultIntakeArtifact,
    )

RESULT_INTAKE_STORE_SCHEMA_VERSION = 1

_INTAKE_FILE = "result_intake.jsonl"
_CHATGPT_STATUS_UPDATES_FILE = "chatgpt_status_updates.jsonl"
_PROJECT_STATE_UPDATES_FILE = "project_state_updates.jsonl"
_NEXT_ACTION_DECISIONS_FILE = "next_action_decisions.jsonl"

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
    if isinstance(value, dict):
        return dict(value)
    return dict(value)


def _artifact_from_dict(payload: dict) -> ResultIntakeArtifact:
    return ResultIntakeArtifact.of(
        payload.get("artifact_id", ""),
        payload.get("artifact_type", ""),
        payload.get("title", ""),
        payload.get("summary", ""),
        path=payload.get("path"),
        sha256=payload.get("sha256"),
        required=bool(payload.get("required", False)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _intake_from_dict(payload: dict) -> AIResultIntakeRecord:
    return AIResultIntakeRecord.of(
        payload.get("intake_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("source_agent", ""),
        payload.get("source_runtime_id", ""),
        payload.get("title", ""),
        payload.get("raw_result_summary", ""),
        payload.get("normalized_summary", ""),
        payload.get("verdict", ""),
        payload.get("confidence", ""),
        payload.get("created_at", ""),
        payload.get("status", "drafted"),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        source_packet_id=payload.get("source_packet_id"),
        source_result_packet_id=payload.get("source_result_packet_id"),
        artifacts=tuple(
            _artifact_from_dict(artifact) for artifact in payload.get("artifacts", ())
        ),
        blockers=tuple(payload.get("blockers", ())),
        warnings=tuple(payload.get("warnings", ())),
        tests_summary=payload.get("tests_summary", ""),
        changed_files_summary=payload.get("changed_files_summary", ""),
        operator_review_required=bool(payload.get("operator_review_required", True)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _chatgpt_status_update_from_dict(payload: dict) -> ChatGPTStatusUpdatePacket:
    return ChatGPTStatusUpdatePacket.of(
        payload.get("update_packet_id", ""),
        payload.get("intake_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("target_runtime_id", ""),
        payload.get("title", ""),
        payload.get("status_update_body", ""),
        payload.get("result_verdict", ""),
        payload.get("result_summary", ""),
        payload.get("requested_chatgpt_action", ""),
        payload.get("created_at", ""),
        payload.get("status", "drafted"),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        target_agent=payload.get("target_agent", "chatgpt"),
        evidence_refs=tuple(payload.get("evidence_refs", ())),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _project_state_update_from_dict(payload: dict) -> ProjectStateUpdate:
    return ProjectStateUpdate.of(
        payload.get("state_update_id", ""),
        payload.get("intake_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("previous_stage", ""),
        payload.get("current_stage", ""),
        payload.get("task_status", ""),
        payload.get("stage_status", ""),
        payload.get("latest_agent", ""),
        payload.get("latest_verdict", ""),
        payload.get("summary", ""),
        payload.get("updated_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        evidence_refs=tuple(payload.get("evidence_refs", ())),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _next_action_decision_from_dict(payload: dict) -> NextActionDecision:
    return NextActionDecision.of(
        payload.get("next_action_id", ""),
        payload.get("intake_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("recommended_action", ""),
        payload.get("priority", "normal"),
        payload.get("reason", ""),
        payload.get("created_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        target_agent=payload.get("target_agent"),
        target_runtime_id=payload.get("target_runtime_id"),
        requires_operator_approval=bool(payload.get("requires_operator_approval", True)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


class ResultIntakeStore:
    """Append-only JSONL store rooted at ``root_dir``.

    Directories are created lazily on the first ``append_*`` call; the
    ``list_*`` methods never create anything and return an empty tuple when
    the backing file does not exist yet.
    """

    def __init__(self, root_dir: Any) -> None:
        self._root_dir = _ensure_local_root(root_dir)

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

    def append_intake(self, record: AIResultIntakeRecord) -> None:
        if not isinstance(record, AIResultIntakeRecord):
            raise ValueError(
                "NOT_AN_AI_RESULT_INTAKE_RECORD: only AIResultIntakeRecord "
                "instances may be stored"
            )
        self._append(_INTAKE_FILE, record.to_dict())

    def append_chatgpt_status_update(self, packet: ChatGPTStatusUpdatePacket) -> None:
        if not isinstance(packet, ChatGPTStatusUpdatePacket):
            raise ValueError(
                "NOT_A_CHATGPT_STATUS_UPDATE_PACKET: only "
                "ChatGPTStatusUpdatePacket instances may be stored"
            )
        self._append(_CHATGPT_STATUS_UPDATES_FILE, packet.to_dict())

    def append_project_state_update(self, update: ProjectStateUpdate) -> None:
        if not isinstance(update, ProjectStateUpdate):
            raise ValueError(
                "NOT_A_PROJECT_STATE_UPDATE: only ProjectStateUpdate "
                "instances may be stored"
            )
        self._append(_PROJECT_STATE_UPDATES_FILE, update.to_dict())

    def append_next_action_decision(self, decision: NextActionDecision) -> None:
        if not isinstance(decision, NextActionDecision):
            raise ValueError(
                "NOT_A_NEXT_ACTION_DECISION: only NextActionDecision "
                "instances may be stored"
            )
        self._append(_NEXT_ACTION_DECISIONS_FILE, decision.to_dict())

    def list_intakes(self) -> tuple[AIResultIntakeRecord, ...]:
        payloads = self._read(_INTAKE_FILE, "INVALID_RESULT_INTAKE_LINE")
        return tuple(_intake_from_dict(payload) for payload in payloads)

    def list_chatgpt_status_updates(self) -> tuple[ChatGPTStatusUpdatePacket, ...]:
        payloads = self._read(
            _CHATGPT_STATUS_UPDATES_FILE, "INVALID_CHATGPT_STATUS_UPDATE_LINE"
        )
        return tuple(_chatgpt_status_update_from_dict(payload) for payload in payloads)

    def list_project_state_updates(self) -> tuple[ProjectStateUpdate, ...]:
        payloads = self._read(
            _PROJECT_STATE_UPDATES_FILE, "INVALID_PROJECT_STATE_UPDATE_LINE"
        )
        return tuple(_project_state_update_from_dict(payload) for payload in payloads)

    def list_next_action_decisions(self) -> tuple[NextActionDecision, ...]:
        payloads = self._read(
            _NEXT_ACTION_DECISIONS_FILE, "INVALID_NEXT_ACTION_DECISION_LINE"
        )
        return tuple(_next_action_decision_from_dict(payload) for payload in payloads)
