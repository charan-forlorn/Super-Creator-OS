"""Stage 8.2 manual file snapshot refresh transport foundation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    from .file_snapshot_transport_models import (
        FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        FileSnapshotTransportError,
        FileSnapshotTransportManifest,
        FileSnapshotTransportResult,
        FileSnapshotTransportSource,
        FrozenMap,
    )
    from .file_snapshot_transport_validation import (
        validate_checked_at,
        validate_local_repo_root,
        validate_no_forbidden_transport_behavior,
        validate_payload_is_json_object,
        validate_snapshot_output_path,
    )
    from .operator_command_views import build_operator_command_view_snapshot
    from .operator_health_activity_facade import query_operator_health_activity_read_models
    from .read_surface_facade import query_control_center_read_surface
    from .transport_activation_decision_gate import run_local_transport_activation_decision_gate
except ImportError:  # direct-module execution
    from file_snapshot_transport_models import (
        FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        FileSnapshotTransportError,
        FileSnapshotTransportManifest,
        FileSnapshotTransportResult,
        FileSnapshotTransportSource,
        FrozenMap,
    )
    from file_snapshot_transport_validation import (
        validate_checked_at,
        validate_local_repo_root,
        validate_no_forbidden_transport_behavior,
        validate_payload_is_json_object,
        validate_snapshot_output_path,
    )
    from operator_command_views import build_operator_command_view_snapshot
    from operator_health_activity_facade import query_operator_health_activity_read_models
    from read_surface_facade import query_control_center_read_surface
    from transport_activation_decision_gate import run_local_transport_activation_decision_gate

_TRANSPORT_MODE = "FILE_SNAPSHOT_REFRESH"
_SOURCE_FILES = (
    "scos/control_center/file_snapshot_transport_models.py",
    "scos/control_center/file_snapshot_transport_validation.py",
    "scos/control_center/file_snapshot_refresh_transport.py",
)


def _stable_json(payload: object, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent, separators=None if indent else (",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    return prefix + _sha256_text("|".join(str(part) for part in parts))[:16]


def _resolved_output(repo_root: Path, output_path) -> Path:
    path = Path(output_path)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _source_from_payload(
    *,
    source_type: str,
    path: str,
    required: bool,
    payload: dict | None,
    warnings: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FileSnapshotTransportSource:
    if blockers:
        status = "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
    elif warnings:
        status = "DEGRADED"
    elif payload is None:
        status = "MISSING_REQUIRED" if required else "MISSING_OPTIONAL"
    else:
        status = "AVAILABLE"
    checksum = None if payload is None else _sha256_text(_stable_json(payload))
    return FileSnapshotTransportSource(
        source_id=_stable_id("fsts-", source_type, path, status, checksum, warnings, blockers),
        source_type=source_type,
        status=status,
        path=path,
        required=required,
        checksum_sha256=checksum,
        warnings=warnings,
        blockers=blockers,
        metadata=FrozenMap.from_mapping(metadata or {}),
    )


def _result_payload(
    *,
    source_type: str,
    result: Any,
) -> tuple[dict | None, tuple[str, ...], tuple[str, ...]]:
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
        warnings = tuple(str(item) for item in payload.get("warnings", ()) if item)
        blockers = tuple(str(item) for item in payload.get("blockers", ()) if item)
        return payload, warnings, blockers
    return None, (), (f"{source_type} public API returned an unsupported result",)


def _collect_sources(
    *,
    repo_root: Path,
    checked_at: str,
    include_read_surface: bool,
    include_operator_health: bool,
    include_approval_commands: bool,
    include_transport_decision: bool,
) -> tuple[tuple[FileSnapshotTransportSource, ...], dict[str, Any]]:
    sources: list[FileSnapshotTransportSource] = []
    payload: dict[str, Any] = {}
    if include_read_surface:
        result = query_control_center_read_surface(
            repo_root=repo_root,
            query_type="FULL_LOCAL_READ_SURFACE",
            checked_at=checked_at,
        )
        source_payload, warnings, blockers = _result_payload(source_type="READ_SURFACE", result=result)
        payload["read_surface"] = source_payload
        sources.append(
            _source_from_payload(
                source_type="READ_SURFACE",
                path="scos.control_center.read_surface_facade.query_control_center_read_surface",
                required=True,
                payload=source_payload,
                warnings=warnings,
                blockers=blockers,
            )
        )
    else:
        payload["read_surface"] = None
        sources.append(
            _source_from_payload(
                source_type="READ_SURFACE",
                path="disabled",
                required=True,
                payload=None,
                blockers=("required read surface source disabled",),
            )
        )

    if include_operator_health:
        result = query_operator_health_activity_read_models(repo_root=repo_root, checked_at=checked_at)
        source_payload, warnings, blockers = _result_payload(source_type="OPERATOR_HEALTH_ACTIVITY", result=result)
        payload["operator_health_activity"] = source_payload
        sources.append(
            _source_from_payload(
                source_type="OPERATOR_HEALTH_ACTIVITY",
                path="scos.control_center.operator_health_activity_facade.query_operator_health_activity_read_models",
                required=False,
                payload=source_payload,
                warnings=warnings,
                blockers=(),
                metadata={"source_blockers_as_warnings": tuple(blockers)},
            )
        )
    else:
        payload["operator_health_activity"] = None
        sources.append(
            _source_from_payload(
                source_type="OPERATOR_HEALTH_ACTIVITY",
                path="disabled",
                required=False,
                payload=None,
                warnings=("optional operator health activity source disabled",),
            )
        )

    if include_approval_commands:
        snapshot = build_operator_command_view_snapshot(checked_at=checked_at, commands=())
        source_payload = snapshot.to_dict()
        payload["approval_aware_command_view"] = source_payload
        sources.append(
            _source_from_payload(
                source_type="APPROVAL_AWARE_COMMAND_VIEW",
                path="scos.control_center.operator_command_views.build_operator_command_view_snapshot",
                required=False,
                payload=source_payload,
                warnings=tuple(snapshot.warnings),
                blockers=(),
            )
        )
    else:
        payload["approval_aware_command_view"] = None
        sources.append(
            _source_from_payload(
                source_type="APPROVAL_AWARE_COMMAND_VIEW",
                path="disabled",
                required=False,
                payload=None,
                warnings=("optional approval-aware command view source disabled",),
            )
        )

    if include_transport_decision:
        result = run_local_transport_activation_decision_gate(
            repo_root=repo_root,
            decided_at=checked_at,
            requested_decision="FILE_SNAPSHOT_REFRESH_ALLOWED_LATER",
            allow_future_implementation=True,
        )
        source_payload, warnings, blockers = _result_payload(source_type="TRANSPORT_DECISION", result=result)
        payload["transport_decision"] = source_payload
        sources.append(
            _source_from_payload(
                source_type="TRANSPORT_DECISION",
                path="scos.control_center.transport_activation_decision_gate.run_local_transport_activation_decision_gate",
                required=True,
                payload=source_payload,
                warnings=warnings,
                blockers=blockers,
            )
        )
    else:
        payload["transport_decision"] = None
        sources.append(
            _source_from_payload(
                source_type="TRANSPORT_DECISION",
                path="disabled",
                required=True,
                payload=None,
                blockers=("required transport decision source disabled",),
            )
        )

    payload["static_fallback"] = {
        "available": True,
        "description": "Manual no-live-transport fallback remains available.",
        "transport_mode": _TRANSPORT_MODE,
    }
    sources.append(
        _source_from_payload(
            source_type="STATIC_FALLBACK",
            path="manual-static-fallback",
            required=False,
            payload=payload["static_fallback"],
        )
    )
    return tuple(sources), payload


def _build_result(
    *,
    repo_root: Path,
    checked_at: str,
    output_path_text: str,
    metadata: dict[str, Any] | None,
    include_read_surface: bool,
    include_operator_health: bool,
    include_approval_commands: bool,
    include_transport_decision: bool,
) -> FileSnapshotTransportResult:
    sources, source_payload = _collect_sources(
        repo_root=repo_root,
        checked_at=checked_at,
        include_read_surface=include_read_surface,
        include_operator_health=include_operator_health,
        include_approval_commands=include_approval_commands,
        include_transport_decision=include_transport_decision,
    )
    warnings = tuple(sorted({item for source in sources for item in source.warnings}))
    blockers = tuple(sorted({item for source in sources if source.required for item in source.blockers}))
    base_payload = {
        "checked_at": checked_at,
        "sources": source_payload,
        "transport_mode": _TRANSPORT_MODE,
    }
    payload_sha = _sha256_text(_stable_json(base_payload))
    snapshot_id = _stable_id(
        "fstr-",
        FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        checked_at,
        _TRANSPORT_MODE,
        tuple((source.source_id, source.status, source.checksum_sha256) for source in sources),
        output_path_text,
    )
    manifest = FileSnapshotTransportManifest(
        schema_version=FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        generated_at=checked_at,
        transport_mode=_TRANSPORT_MODE,
        repo_root=str(repo_root),
        output_path=output_path_text,
        source_count=len(sources),
        payload_sha256=payload_sha,
        sources=sources,
        warnings=warnings,
        blockers=blockers,
        metadata=FrozenMap.from_mapping(metadata or {}),
    )
    payload = dict(base_payload)
    payload["snapshot_id"] = snapshot_id
    accepted = not blockers
    return FileSnapshotTransportResult(
        accepted=accepted,
        go_no_go="GO" if accepted else "NO_GO",
        readiness_score=100 if accepted else max(70, 95 - len(blockers) * 5),
        snapshot_id=snapshot_id,
        output_path=output_path_text or None,
        manifest=manifest,
        payload=payload,
        warnings=warnings,
        blockers=blockers,
        checked_at=checked_at,
    )


def build_file_snapshot_transport_payload(
    *,
    repo_root,
    checked_at: str,
    include_read_surface: bool = True,
    include_operator_health: bool = True,
    include_approval_commands: bool = True,
    include_transport_decision: bool = True,
    metadata=None,
) -> FileSnapshotTransportResult | FileSnapshotTransportError:
    checked_ok, checked_errors = validate_checked_at(checked_at)
    root_ok, root_errors = validate_local_repo_root(repo_root)
    if not checked_ok or not root_ok:
        errors = tuple(sorted(set(checked_errors + root_errors)))
        return FileSnapshotTransportError.of(
            "INVALID_FILE_SNAPSHOT_TRANSPORT_INPUT",
            errors[0],
            checked_at=str(checked_at),
            blockers=errors,
        )
    root = Path(repo_root).resolve()
    return _build_result(
        repo_root=root,
        checked_at=str(checked_at),
        output_path_text="",
        metadata=dict(metadata or {}),
        include_read_surface=include_read_surface,
        include_operator_health=include_operator_health,
        include_approval_commands=include_approval_commands,
        include_transport_decision=include_transport_decision,
    )


def refresh_file_snapshot_transport(
    *,
    repo_root,
    output_path,
    checked_at: str,
    include_read_surface: bool = True,
    include_operator_health: bool = True,
    include_approval_commands: bool = True,
    include_transport_decision: bool = True,
    metadata=None,
    overwrite: bool = False,
) -> FileSnapshotTransportResult | FileSnapshotTransportError:
    checked_ok, checked_errors = validate_checked_at(checked_at)
    path_ok, path_errors = validate_snapshot_output_path(repo_root=repo_root, output_path=output_path)
    if not checked_ok or not path_ok:
        errors = tuple(sorted(set(checked_errors + path_errors)))
        return FileSnapshotTransportError.of(
            "INVALID_FILE_SNAPSHOT_TRANSPORT_REFRESH_INPUT",
            errors[0],
            checked_at=str(checked_at),
            blockers=errors,
        )
    root = Path(repo_root).resolve()
    resolved_output = _resolved_output(root, output_path)
    if resolved_output.exists() and not overwrite:
        return FileSnapshotTransportError.of(
            "FILE_SNAPSHOT_OUTPUT_EXISTS",
            "output_path already exists and overwrite=False",
            checked_at=str(checked_at),
            blockers=("output_path already exists and overwrite=False",),
        )
    result = _build_result(
        repo_root=root,
        checked_at=str(checked_at),
        output_path_text=str(resolved_output),
        metadata=dict(metadata or {}),
        include_read_surface=include_read_surface,
        include_operator_health=include_operator_health,
        include_approval_commands=include_approval_commands,
        include_transport_decision=include_transport_decision,
    )
    if result.blockers:
        return result
    assert result.manifest is not None
    assert result.payload is not None
    document = {
        "schema_version": FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        "snapshot_id": result.snapshot_id,
        "generated_at": str(checked_at),
        "transport_mode": _TRANSPORT_MODE,
        "manifest": result.manifest.to_dict(),
        "payload": result.payload,
        "warnings": list(result.warnings),
        "blockers": list(result.blockers),
    }
    ok, errors = validate_payload_is_json_object(document)
    if not ok:
        return FileSnapshotTransportError.of(
            "INVALID_FILE_SNAPSHOT_TRANSPORT_PAYLOAD",
            errors[0],
            checked_at=str(checked_at),
            blockers=errors,
        )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(_stable_json(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    return replace(result, output_path=str(resolved_output))


def validate_file_snapshot_transport_boundary(
    *,
    repo_root,
    checked_at: str,
) -> dict:
    checked_ok, checked_errors = validate_checked_at(checked_at)
    root_ok, root_errors = validate_local_repo_root(repo_root)
    blockers = list(checked_errors + root_errors)
    findings: list[str] = []
    if root_ok:
        root = Path(repo_root).resolve()
        for rel_path in _SOURCE_FILES:
            path = root / rel_path
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            ok, scan_findings = validate_no_forbidden_transport_behavior(text)
            if not ok:
                findings.extend(f"{rel_path}: {finding}" for finding in scan_findings)
    blockers.extend(findings)
    return {
        "ok": checked_ok and root_ok and not blockers,
        "checked_at": str(checked_at),
        "blockers": tuple(sorted(set(blockers))),
        "warnings": (),
        "manual_refresh_only": True,
        "implicit_writes": False,
        "background_process": False,
        "file_watcher": False,
        "polling": False,
        "network": False,
        "command_execution": False,
        "forbidden_behavior_findings": tuple(sorted(set(findings))),
    }


__all__ = sorted(
    (
        "build_file_snapshot_transport_payload",
        "refresh_file_snapshot_transport",
        "validate_file_snapshot_transport_boundary",
    )
)
