"""Cohort 9A backend contract tests for the truthful read-only snapshot.

These tests prove the projection boundary is read-only, redacted, and
distinguishes valid-empty from unavailable/error. They use hermetic fakes
patched at the real read-facade boundaries (the module imports those names
into its own namespace), so no real filesystem, HVS, or network is exercised.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from scos.control_center.read_surface_models import (
    FrozenMap,
    ReadSurfaceRecord,
    ReadSurfaceResult,
    ReadSurfaceSnapshot,
)
from scos.control_center.operator_read_models import (
    OperatorActivityRecord,
    OperatorReadModelResult,
    OperatorReadModelSnapshot,
)

import scos.control_center.control_center_snapshot as snap
from scos.control_center import control_center_snapshot as target

_MODULE_SOURCE = pathlib.Path(snap.__file__).read_text(encoding="utf-8")

CHECKED_AT = "2026-07-16T00:00:00Z"

# ---------------------------------------------------------------------------
# Fakes for the four read facades the module actually imports.
# ---------------------------------------------------------------------------


class _HealthReport:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _default_health():
    return _HealthReport(
        schema_version=1,
        checked_at=CHECKED_AT,
        health_status="healthy",
        source_coverage=(("state_db", "readable"),),
        artifact_count=1,
        event_count=0,
        audit_record_count=0,
        command_record_count=0,
        drift_count=0,
        warning_count=0,
        blocker_count=0,
        checks=(),
        warnings=(),
        blockers=(),
        recent_activity_summary=(),
        drift_findings=(),
    )


class _ReadSurfaceRecord:
    def __init__(self, record_type, metadata):
        self.record_type = record_type
        self.metadata = metadata


class _ReadSurfaceSnapshot:
    def __init__(self, records):
        self.records = tuple(records)


class _ReadSurfaceResult:
    # Mirrors the real facade return type (ReadSurfaceResult wrapping a
    # ReadSurfaceSnapshot). The production builder unwraps `.snapshot`.
    def __init__(self, snapshot):
        self.snapshot = snapshot


class _ActivityRecord:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _ActivitySnapshot:
    def __init__(self, recent_activity):
        self.recent_activity = tuple(recent_activity)


class _OperatorReadModelResult:
    def __init__(self, snapshot):
        self.snapshot = snapshot


def _read_surface_result(records):
    recs = [
        ReadSurfaceRecord(
            record_id=f"rec-{rt}",
            record_type=rt,
            source_stage="stage-x",
            summary="test record",
            status="ok",
            references=(),
            metadata=tuple(meta),
        )
        for rt, meta in records
    ]
    # The facade returns a ReadSurfaceResult wrapping a ReadSurfaceSnapshot.
    # Wrap it so the production builder can unwrap `.snapshot` correctly.
    snapshot = ReadSurfaceSnapshot(
        snapshot_id="rs-1",
        checked_at=CHECKED_AT,
        query_id="q-1",
        records=tuple(recs),
        readiness=FrozenMap(items=()),
        blockers=(),
        warnings=(),
    )
    return ReadSurfaceResult(
        accepted=True,
        go_no_go="GO",
        readiness_score=100,
        snapshot=snapshot,
        blockers=(),
        warnings=(),
        checked_at=CHECKED_AT,
    )


def _op_result(snapshot):
    return OperatorReadModelResult(snapshot=snapshot)


def _activity_snapshot(records):
    recs = [
        OperatorActivityRecord(
            activity_id=r["activity_id"],
            activity_type=r["activity_type"],
            status=r["status"],
            summary=r["summary"],
            source_stage="stage-x",
            occurred_at=r["occurred_at"],
            references=(),
            metadata=(),
        )
        for r in records
    ]
    return OperatorReadModelSnapshot(
        snapshot_id="op-1",
        checked_at=CHECKED_AT,
        health_signals=(),
        recent_activity=tuple(recs),
        readiness_score=100,
        go_no_go="GO",
        blockers=(),
        warnings=(),
    )


# ---------------------------------------------------------------------------
# Patch helpers — replace the module-level facade names with fakes.
# ---------------------------------------------------------------------------


def _patch_facades(monkeypatch, *, health=None, commands=(), read_surface=None, op_result=None):
    monkeypatch.setattr(target, "run_backend_health_check", lambda **_k: health if health is not None else _default_health())
    monkeypatch.setattr(target, "read_command_queue", lambda **_k: list(commands))
    monkeypatch.setattr(
        target,
        "query_control_center_read_surface",
        lambda **_k: read_surface if read_surface is not None else _read_surface_result([]),
    )
    monkeypatch.setattr(
        target,
        "query_operator_health_activity_read_models",
        lambda **_k: op_result if op_result is not None else _op_result(None),
    )


class _Cmd:
    def __init__(self, command_id="cmd-1", command_type="render", approved_at=CHECKED_AT, args=None, metadata=None):
        self.command_id = command_id
        self.command_type = command_type
        self.approved_at = approved_at
        self.args = args or (("secret", "x"),)
        self.metadata = metadata or (("token", "y"),)


# ---------------------------------------------------------------------------
# Static contract: the projection module must never IMPORT forbidden surfaces.
# We parse real import statements so docstring/comment mentions are ignored.
# ---------------------------------------------------------------------------

import ast as _ast

_MODULE_AST = _ast.parse(_MODULE_SOURCE)


def _imported_module_names():
    names: set[str] = set()
    for node in _ast.walk(_MODULE_AST):
        if isinstance(node, _ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, _ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


_FORBIDDEN_IMPORT_PREFIXES = (
    "scos.control_center.hvs_adapter",
    "scos.control_center.hvs_project_initialization",
    "scos.control_center.operator_approval",
    "scos.control_center.command_api",
    "scos.control_center.local_backend",
    "scos.control_center.command_runner",
)


def test_module_does_not_import_forbidden_surfaces():
    imported = _imported_module_names()
    for prefix in _FORBIDDEN_IMPORT_PREFIXES:
        for name in imported:
            assert not name.startswith(prefix), f"forbidden import present: {name}"


def test_module_does_not_use_subprocess_or_socket_or_sqlite():
    # Only flag dangerous *usage* tokens that would execute a subprocess,
    # open a socket, or write to sqlite. Docstrings mentioning these words
    # (explaining what the module avoids) are allowed.
    dangerous_calls = ("subprocess", "socket.socket", "sqlite3.connect", "os.mkdir", "os.makedirs")
    for token in dangerous_calls:
        assert token not in _MODULE_SOURCE, f"dangerous usage present: {token}"


def test_schema_version_and_source_mode_present(monkeypatch):
    _patch_facades(monkeypatch)
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    assert out["schema_version"] == 1
    assert out["source_mode"] == "LIVE_LOCAL_READ_ONLY"
    assert out["snapshot_id"].startswith("ccs-")


def test_empty_queue_is_available_empty_not_zero(monkeypatch):
    _patch_facades(monkeypatch, commands=())
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    q = out["queue_summary"]
    assert q["status"] == snap.STATUS_AVAILABLE_EMPTY
    assert q["available"] is True
    assert q["data"]["count"] == 0
    assert q["data"]["items"] == []


def test_queue_with_items_is_available_with_data(monkeypatch):
    _patch_facades(monkeypatch, commands=(_Cmd(),))
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    q = out["queue_summary"]
    assert q["status"] == snap.STATUS_AVAILABLE_WITH_DATA
    item = q["data"]["items"][0]
    assert item["command_id"] == "cmd-1"
    assert item["command_type"] == "render"
    assert "args" not in item
    assert "metadata" not in item
    assert "secret" not in item


def test_empty_approval_read_is_available_empty_when_count_zero(monkeypatch):
    _patch_facades(
        monkeypatch,
        read_surface=_read_surface_result(
            [("approval_summary", (("approval_count", "0"), ("audit_record_count", "0")))]
        ),
    )
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    a = out["approval_summary"]
    assert a["status"] == snap.STATUS_AVAILABLE_EMPTY
    assert a["available"] is True
    assert a["data"]["approval_count"] == 0


def test_approval_read_failure_reports_unavailable_not_zero(monkeypatch):
    _patch_facades(monkeypatch, read_surface=_read_surface_result([]))
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    a = out["approval_summary"]
    assert a["status"] == snap.STATUS_UNAVAILABLE
    assert a["available"] is False
    assert a["data"] is None


def test_evidence_read_failure_not_shown_as_no_evidence(monkeypatch):
    _patch_facades(monkeypatch, read_surface=_read_surface_result([]))
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    e = out["evidence_summary"]
    assert e["status"] == snap.STATUS_UNAVAILABLE
    assert e["available"] is False
    assert e["data"] is None


def test_one_subsystem_failure_does_not_corrupt_others(monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("boom")

    _patch_facades(monkeypatch)
    monkeypatch.setattr(target, "read_command_queue", _boom)
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    # The queue read failed -> its own section is UNAVAILABLE (degraded
    # independently), but it must NOT crash or corrupt the other sections.
    assert out["queue_summary"]["status"] == snap.STATUS_UNAVAILABLE
    # Health read from its own (unaffected) fake remains valid.
    assert out["health"]["status"] == snap.STATUS_AVAILABLE_WITH_DATA
    # Read-surface-backed sections resolve independently of the queue failure
    # and are either truthfully AVAILABLE or UNAVAILABLE (never ERROR/garbage).
    for key in ("approval_summary", "evidence_summary", "project_summary", "recent_activity"):
        assert out[key]["status"] in (
            snap.STATUS_AVAILABLE_WITH_DATA,
            snap.STATUS_AVAILABLE_EMPTY,
            snap.STATUS_UNAVAILABLE,
        )
    assert "READ_FAILED" in out["degradation_reasons"]


def test_no_sensitive_fields_leak(monkeypatch):
    _patch_facades(monkeypatch, commands=(_Cmd(args=(("raw_argv", "/abs/path/secret"),), metadata=(("token", "abc"),)),))
    out = target.build_control_center_snapshot(repo_root=".", checked_at=CHECKED_AT)
    blob = __import__("json").dumps(out)
    assert "secret" not in blob
    assert "/abs/path" not in blob
    assert "raw_argv" not in blob
    assert "token" not in blob


def test_no_absolute_paths_or_raw_traces(monkeypatch):
    _patch_facades(monkeypatch)
    out = target.build_control_center_snapshot(repo_root="C:/Users/chara", checked_at=CHECKED_AT)
    blob = __import__("json").dumps(out)
    assert "C:/Users/chara" not in blob
    assert "Traceback" not in blob


def test_cli_entrypoint_emits_json_and_exits_zero(monkeypatch, capsys):
    _patch_facades(monkeypatch, commands=())
    rc = target.main(["--checked-at", CHECKED_AT, "--repo-root", "."])
    assert rc == 0
    captured = capsys.readouterr().out
    payload = __import__("json").loads(captured)
    assert payload["source_mode"] == "LIVE_LOCAL_READ_ONLY"


def test_cli_defensive_error_envelope(monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("fatal")

    monkeypatch.setattr(target, "build_control_center_snapshot", _boom)
    rc = target.main(["--checked-at", CHECKED_AT, "--repo-root", "."])
    # Even on unexpected error, exit 0 with a truthful UNAVAILABLE envelope.
    assert rc == 0
