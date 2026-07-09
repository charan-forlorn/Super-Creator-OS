"""Stage 8.2 file snapshot transport model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.file_snapshot_transport_models import (
    FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
    FileSnapshotTransportManifest,
    FileSnapshotTransportSource,
    FrozenMap,
)

_NOW = "2026-07-10T06:00:00Z"


def _source() -> FileSnapshotTransportSource:
    return FileSnapshotTransportSource(
        source_id="s1",
        source_type="READ_SURFACE",
        status="AVAILABLE",
        path="public.api",
        required=True,
        checksum_sha256="abc",
        warnings=("z", "a"),
        blockers=(),
        metadata=FrozenMap.from_mapping({"b": 2, "a": {"nested": ["x"]}}),
    )


def test_source_model_is_immutable_and_deterministic() -> None:
    source = _source()

    assert source.warnings == ("a", "z")
    assert source.to_dict()["metadata"] == {"a": {"nested": ["x"]}, "b": 2}
    with pytest.raises(FrozenInstanceError):
        source.status = "DEGRADED"  # type: ignore[misc]


def test_nested_metadata_cannot_be_mutated_through_model_storage() -> None:
    source_mapping = {"nested": {"items": ["a", "b"]}}
    frozen = FrozenMap.from_mapping(source_mapping)
    source_mapping["nested"]["items"].append("c")

    assert frozen.to_dict() == {"nested": {"items": ["a", "b"]}}
    with pytest.raises(FrozenInstanceError):
        frozen.items = ()  # type: ignore[misc]


def test_manifest_to_dict_is_stable_and_sorts_sources() -> None:
    source_a = _source()
    source_b = FileSnapshotTransportSource(
        source_id="a0",
        source_type="STATIC_FALLBACK",
        status="AVAILABLE",
        path="fallback",
        required=False,
        checksum_sha256="def",
        warnings=(),
        blockers=(),
        metadata=FrozenMap.from_mapping({}),
    )
    manifest = FileSnapshotTransportManifest(
        schema_version=FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
        snapshot_id="snap",
        generated_at=_NOW,
        transport_mode="FILE_SNAPSHOT_REFRESH",
        repo_root=".",
        output_path="",
        source_count=2,
        payload_sha256="payload",
        sources=(source_a, source_b),
        warnings=("w",),
        blockers=(),
        metadata=FrozenMap.from_mapping({"stage": "8.2"}),
    )

    payload = manifest.to_dict()
    assert [source["source_id"] for source in payload["sources"]] == ["a0", "s1"]
    assert payload == manifest.to_dict()


def test_manifest_rejects_mismatched_source_count() -> None:
    with pytest.raises(ValueError):
        FileSnapshotTransportManifest(
            schema_version=FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION,
            snapshot_id="snap",
            generated_at=_NOW,
            transport_mode="FILE_SNAPSHOT_REFRESH",
            repo_root=".",
            output_path="",
            source_count=2,
            payload_sha256="payload",
            sources=(_source(),),
            warnings=(),
            blockers=(),
            metadata=FrozenMap.from_mapping({}),
        )


def test_invalid_source_type_and_status_are_rejected() -> None:
    with pytest.raises(ValueError):
        FileSnapshotTransportSource(
            source_id="s1",
            source_type="REMOTE",
            status="AVAILABLE",
            path="x",
            required=False,
            checksum_sha256=None,
            warnings=(),
            blockers=(),
            metadata=FrozenMap.from_mapping({}),
        )
    with pytest.raises(ValueError):
        FileSnapshotTransportSource(
            source_id="s1",
            source_type="UNKNOWN",
            status="OK",
            path="x",
            required=False,
            checksum_sha256=None,
            warnings=(),
            blockers=(),
            metadata=FrozenMap.from_mapping({}),
        )
