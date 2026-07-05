"""SCOS Stage 5.1 local Control Center command bridge.

First local-first bridge between the SCOS Control Center concept and the local
SCOS command system: draft -> validate -> operator approval -> JSONL queue ->
allowlisted local runner -> JSONL event log.

Stage 5.1 note: exports are resolved lazily via PEP 562 module ``__getattr__``
(mirroring ``scos.commercial``) so importing this package never eagerly pulls
in sibling modules. The package is stdlib-only and never imports
``scos.commercial`` or ``scos.knowledge`` in-process.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no database.
"""

from __future__ import annotations

from typing import Any

# name -> sibling module that defines it (imported on first access only)
_LAZY_EXPORTS: dict[str, str] = {
    "CONTROL_CENTER_COMMAND_SCHEMA_VERSION": "command_models",
    "ALLOWED_COMMAND_TYPES": "command_models",
    "ALLOWED_EVENT_TYPES": "command_models",
    "ALLOWED_EVENT_STATUSES": "command_models",
    "CommandDraft": "command_models",
    "OperatorApproval": "command_models",
    "ApprovedCommand": "command_models",
    "CommandResult": "command_models",
    "CommandEvent": "command_models",
    "CONTROL_CENTER_COMMAND_VALIDATION_SCHEMA_VERSION": "command_validation",
    "validate_command_type": "command_validation",
    "validate_command_args": "command_validation",
    "validate_no_forbidden_command_text": "command_validation",
    "validate_command_draft": "command_validation",
    "CONTROL_CENTER_OPERATOR_APPROVAL_SCHEMA_VERSION": "operator_approval",
    "approve_command": "operator_approval",
    "reject_command": "operator_approval",
    "create_approved_command": "operator_approval",
    "CONTROL_CENTER_COMMAND_QUEUE_SCHEMA_VERSION": "command_queue",
    "append_approved_command": "command_queue",
    "read_command_queue": "command_queue",
    "CONTROL_CENTER_EVENT_LOG_SCHEMA_VERSION": "event_log",
    "append_command_event": "event_log",
    "read_command_events": "event_log",
    "make_command_event": "event_log",
    "CONTROL_CENTER_COMMAND_RUNNER_SCHEMA_VERSION": "command_runner",
    "run_approved_command": "command_runner",
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
