"""Shared bounded authority for commercial test suite verification.

This module centralizes:
- nested-suite re-entry detection
- bounded subprocess execution
- process-tree termination on timeout
- deterministic failure reporting

Environment marker:
    SCOS_COMMERCIAL_EXISTING_SUITES_NESTED=1

Public contract:
    is_nested_suite_run() -> bool
    run_existing_suites(suites, *, timeout_seconds) -> None
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

_NESTED_ENV_VAR = "SCOS_COMMERCIAL_EXISTING_SUITES_NESTED"
_DEFAULT_TIMEOUT = 120.0


def is_nested_suite_run() -> bool:
    """Return True when this call is executing inside a nested child suite."""
    return os.environ.get(_NESTED_ENV_VAR) == "1"


def run_existing_suites(
    suites,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> None:
    """Run each suite path once with bounded timeout and re-entry guard.

    Raises AssertionError on any non-zero exit or timeout.
    """
    if is_nested_suite_run():
        return

    for suite in suites:
        _run_single_suite(suite, timeout_seconds=timeout_seconds)


def _run_single_suite(suite: Path, *, timeout_seconds: float) -> None:
    child_env = os.environ.copy()
    child_env[_NESTED_ENV_VAR] = "1"

    cmd = [sys.executable, str(suite)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(suite.resolve().parent),
            env=child_env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        pid = getattr(exc, "pid", None)
        if pid is not None:
            _terminate_process_tree(pid)
        stdout_text = ""
        stderr_text = ""
        if exc.stdout:
            stdout_text = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        if exc.stderr:
            stderr_text = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        raise AssertionError(
            f"suite timed out after {timeout_seconds}s: {suite.name}\n"
            f"stdout (bounded):\n{_bounded_text(stdout_text)}\n"
            f"stderr (bounded):\n{_bounded_text(stderr_text)}"
        ) from exc

    if proc.returncode != 0:
        raise AssertionError(
            f"suite failed (exit={proc.returncode}): {suite.name}\n"
            f"stdout (bounded):\n{_bounded_text(proc.stdout)}\n"
            f"stderr (bounded):\n{_bounded_text(proc.stderr)}"
        )


def _terminate_process_tree(pid: int) -> None:
    """Best-effort termination of the task-owned child process tree."""
    try:
        if sys.platform == "win32":
            # Windows: create a new process group so we can signal the tree.
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GENERIC_TERM = 0x10000000
            killed = False

            for try_pid in (pid,):
                if try_pid <= 0:
                    continue
                h = kernel32.OpenProcess(GENERIC_TERM, False, try_pid)
                if not h:
                    continue
                kernel32.TerminateProcess(h, 1)
                kernel32.CloseHandle(h)
                killed = True
                break
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _bounded_text(text: str | None, limit: int = 4000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...[truncated]...\n" + text[-limit // 2 :]
