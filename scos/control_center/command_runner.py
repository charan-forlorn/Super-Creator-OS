"""SCOS Stage 5.1 allowlisted local command runner.

Executes ONLY the six allowlisted Stage 5.1 command types, and only for an
``ApprovedCommand``. Every subprocess uses list arguments (never
``shell=True``), a finite deterministic timeout, and captured stdout/stderr
truncated to a fixed excerpt length. Git usage is limited to the four
read-only status-snapshot queries; no git mutating command can be produced
by this module.

``dry_run=True`` never spawns a subprocess: the planned command is returned
in the result metadata only.

Local-first, deterministic, stdlib-only. No clock (``started_at`` /
``finished_at`` are caller-supplied), no random, no network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from .command_models import ALLOWED_COMMAND_TYPES, ApprovedCommand, CommandResult
    from .event_log import append_command_event, make_command_event
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_models import ALLOWED_COMMAND_TYPES, ApprovedCommand, CommandResult
    from event_log import append_command_event, make_command_event

try:
    from .approval_audit_store import is_execution_granted, verify_chain
except ImportError:  # direct-module execution (tests insert the package dir)
    from approval_audit_store import is_execution_granted, verify_chain

CONTROL_CENTER_COMMAND_RUNNER_SCHEMA_VERSION = 1

COMMAND_TIMEOUT_SECONDS = 900
EXCERPT_LIMIT = 4000

_STAGE5_HANDOFF_DOC = Path("docs") / "roadmap" / "STAGE5_HANDOFF.md"

_SCRIPT_COMMANDS = {
    "RUN_SMOKE_CHECK": "scripts/test_smoke.py",
    "RUN_RELEASE_CHECK": "scripts/test_release.py",
    "RUN_SECURITY_SCAN": "scripts/security_scan_baseline.py",
}

# Read-only git queries only; the runner can never assemble a mutating git call.
_GIT_SNAPSHOT_COMMANDS = (
    ("git", "status", "--short", "--untracked-files=all"),
    ("git", "rev-parse", "HEAD"),
    ("git", "rev-parse", "origin/main"),
    ("git", "branch", "--show-current"),
)


def _interpreter(repo_root: Path) -> str:
    """Windows venv interpreter when present, else the current interpreter."""
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def _excerpt(text: str) -> str:
    return str(text or "")[:EXCERPT_LIMIT]


def _stage4_gate_code(checked_at: str) -> str:
    """Python -c body that runs the Stage 4.19 final release gate in-place."""
    return (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from scos.commercial.stage4_final_release_gate import "
        "run_stage4_final_release_gate\n"
        "result = run_stage4_final_release_gate(\n"
        "    repo_root=Path('.'),\n"
        f"    checked_at={checked_at!r},\n"
        "    output_path=None,\n"
        "    require_clean_git=True,\n"
        "    run_smoke=True,\n"
        "    run_security_scan=True,\n"
        "    run_release_script=True,\n"
        ")\n"
        "payload = result.to_dict()\n"
        "print(json.dumps(payload, sort_keys=True))\n"
        "sys.exit(0 if payload.get('ok') else 1)\n"
    )


def _plan_command(
    repo_root: Path,
    command_type: str,
    args: dict[str, str],
) -> tuple[tuple[tuple[str, ...], ...], str]:
    """Return (subprocess argv tuples, human-readable planned text)."""
    if command_type in _SCRIPT_COMMANDS:
        argv = (_interpreter(repo_root), _SCRIPT_COMMANDS[command_type])
        return (argv,), " ".join(argv)
    if command_type == "RUN_STAGE4_FINAL_GATE":
        argv = (_interpreter(repo_root), "-c", _stage4_gate_code(args["checked_at"]))
        planned = f"{argv[0]} -c <run_stage4_final_release_gate checked_at={args['checked_at']}>"
        return (argv,), planned
    if command_type == "GENERATE_STATUS_SNAPSHOT":
        planned = " ; ".join(" ".join(argv) for argv in _GIT_SNAPSHOT_COMMANDS)
        return _GIT_SNAPSHOT_COMMANDS, planned
    # OPEN_STAGE5_HANDOFF: no subprocess at all.
    return (), f"verify {_STAGE5_HANDOFF_DOC.as_posix()} exists"


def _log_event(
    event_log_path,
    *,
    command_id: str,
    event_type: str,
    created_at: str,
    status: str,
    message: str,
) -> None:
    if event_log_path is None:
        return
    append_command_event(
        event_log_path=event_log_path,
        event=make_command_event(
            command_id=command_id,
            event_type=event_type,
            created_at=created_at,
            status=status,
            message=message,
        ),
    )


def _blocked_result(
    approved_command: ApprovedCommand,
    started_at: str,
    finished_at: str,
    reason: str,
    event_log_path,
) -> CommandResult:
    _log_event(
        event_log_path,
        command_id=approved_command.command_id,
        event_type="COMMAND_BLOCKED",
        created_at=finished_at,
        status="blocked",
        message=reason,
    )
    return CommandResult.of(
        command_id=approved_command.command_id,
        command_type=approved_command.command_type,
        ok=False,
        exit_code=-1,
        started_at=started_at,
        finished_at=finished_at,
        stderr_excerpt=_excerpt(reason),
        metadata=(("blocked", "true"), ("blocked_reason", reason)),
    )


def run_approved_command(
    *,
    repo_root,
    approved_command: ApprovedCommand,
    started_at: str,
    finished_at: str,
    event_log_path=None,
    dry_run: bool = False,
    enforce_audit_grant: bool = False,
    audit_repo_root=None,
    audit_db_path=None,
) -> CommandResult:
    """Run one approved, allowlisted command and return its deterministic result.

    Only ``ApprovedCommand`` instances are accepted (an unapproved draft can
    never execute). Unknown command types and missing required args produce a
    blocked result (never an execution). When ``event_log_path`` is provided,
    the lifecycle is recorded as COMMAND_STARTED then COMMAND_COMPLETED /
    COMMAND_FAILED (or COMMAND_BLOCKED for a never-started command).

    Stage 6.7: when ``enforce_audit_grant`` is True, the Stage 6.6
    tamper-evident approval-audit ledger is the SINGLE source of execution
    grant. The command is blocked unless the latest persisted decision for
    its command id is ``approved`` AND the ledger hash chain is intact. This
    is opt-in (default False) so pre-6.7 callers that do not wire a ledger
    are unchanged. ``audit_repo_root``/``audit_db_path`` default to the same
    ``repo_root`` used for persistence at the approval gate; pass them
    explicitly only when storage locations differ.
    """
    if not isinstance(approved_command, ApprovedCommand):
        raise ValueError(
            "NOT_AN_APPROVED_COMMAND: run_approved_command only accepts ApprovedCommand"
        )
    root = Path(repo_root)
    command_type = approved_command.command_type
    args = dict(approved_command.args)

    if enforce_audit_grant:
        _audit_repo = audit_repo_root if audit_repo_root is not None else root
        if not verify_chain(repo_root=_audit_repo, db_path=audit_db_path):
            return _blocked_result(
                approved_command,
                started_at,
                finished_at,
                "audit ledger tamper detected: hash chain invalid",
                event_log_path,
            )
        if not is_execution_granted(
            subject_type="command",
            subject_id=approved_command.command_id,
            repo_root=_audit_repo,
            db_path=audit_db_path,
        ):
            return _blocked_result(
                approved_command,
                started_at,
                finished_at,
                "execution not granted by approval-audit ledger",
                event_log_path,
            )

    if command_type not in ALLOWED_COMMAND_TYPES:
        return _blocked_result(
            approved_command,
            started_at,
            finished_at,
            f"unknown command_type: {command_type!r}",
            event_log_path,
        )
    if command_type == "RUN_STAGE4_FINAL_GATE" and not args.get("checked_at", "").strip():
        return _blocked_result(
            approved_command,
            started_at,
            finished_at,
            "missing required arg: checked_at",
            event_log_path,
        )

    commands, planned = _plan_command(root, command_type, args)
    base_metadata = (
        ("planned_command", planned),
        ("dry_run", "true" if dry_run else "false"),
    )

    _log_event(
        event_log_path,
        command_id=approved_command.command_id,
        event_type="COMMAND_STARTED",
        created_at=started_at,
        status="pending",
        message=f"{command_type} started",
    )

    if dry_run:
        _log_event(
            event_log_path,
            command_id=approved_command.command_id,
            event_type="COMMAND_COMPLETED",
            created_at=finished_at,
            status="success",
            message=f"{command_type} dry-run: no subprocess executed",
        )
        return CommandResult.of(
            command_id=approved_command.command_id,
            command_type=command_type,
            ok=True,
            exit_code=0,
            started_at=started_at,
            finished_at=finished_at,
            metadata=base_metadata,
        )

    if command_type == "OPEN_STAGE5_HANDOFF":
        handoff = root / _STAGE5_HANDOFF_DOC
        ok = handoff.is_file()
        stdout_text = (
            f"stage5 handoff doc present: {_STAGE5_HANDOFF_DOC.as_posix()}"
            if ok
            else ""
        )
        stderr_text = (
            "" if ok else f"stage5 handoff doc missing: {_STAGE5_HANDOFF_DOC.as_posix()}"
        )
        exit_code = 0 if ok else 1
    else:
        ok = True
        exit_code = 0
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        for argv in commands:
            try:
                proc = subprocess.run(
                    list(argv),
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                ok = False
                exit_code = -1
                stderr_parts.append(f"{type(exc).__name__}: could not run command")
                break
            stdout_parts.append(proc.stdout or "")
            stderr_parts.append(proc.stderr or "")
            if proc.returncode != 0:
                ok = False
                exit_code = int(proc.returncode)
                break
        stdout_text = "".join(stdout_parts)
        stderr_text = "".join(stderr_parts)

    _log_event(
        event_log_path,
        command_id=approved_command.command_id,
        event_type="COMMAND_COMPLETED" if ok else "COMMAND_FAILED",
        created_at=finished_at,
        status="success" if ok else "failure",
        message=f"{command_type} exit_code={exit_code}",
    )
    return CommandResult.of(
        command_id=approved_command.command_id,
        command_type=command_type,
        ok=ok,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
        stdout_excerpt=_excerpt(stdout_text),
        stderr_excerpt=_excerpt(stderr_text),
        metadata=base_metadata,
    )
