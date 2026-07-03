"""SCOS Stage 4.11 first outreach launch kit models.

Immutable, local-first models for deterministic first outreach preparation.
These models reuse the Stage 4.1 ``FrozenMap`` implementation and serialize
with explicit key order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION = 1

OUTREACH_CHECK_STATUSES = ("success", "failure", "skipped")
OUTREACH_CHECK_SEVERITIES = ("info", "warning", "error")
OUTREACH_GO_NO_GO = ("GO", "CONDITIONAL_GO", "NO_GO")


@dataclass(frozen=True)
class OutreachLaunchProfile:
    profile_id: str
    operator_name: str
    target_market: str
    target_location: str
    primary_offer: str
    starting_price: str
    delivery_window: str
    outreach_goal: str
    allowed_channels: tuple[str, ...]
    excluded_channels: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", str(self.profile_id))
        object.__setattr__(self, "operator_name", str(self.operator_name))
        object.__setattr__(self, "target_market", str(self.target_market))
        object.__setattr__(self, "target_location", str(self.target_location))
        object.__setattr__(self, "primary_offer", str(self.primary_offer))
        object.__setattr__(self, "starting_price", str(self.starting_price))
        object.__setattr__(self, "delivery_window", str(self.delivery_window))
        object.__setattr__(self, "outreach_goal", str(self.outreach_goal))
        object.__setattr__(self, "allowed_channels", tuple(str(v) for v in self.allowed_channels))
        object.__setattr__(self, "excluded_channels", tuple(str(v) for v in self.excluded_channels))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def default() -> "OutreachLaunchProfile":
        return OutreachLaunchProfile.of(
            profile_id="first-outreach-launch-001",
            operator_name="SCOS Operator",
            target_market="local clinics and service businesses",
            target_location="local market",
            primary_offer="AI Content & Booking Readiness Audit",
            starting_price="4900 THB",
            delivery_window="24-48 hours after receiving complete inputs",
            outreach_goal="Start manual first-customer outreach with a clear offer and repeatable handoff process.",
            allowed_channels=(
                "manual_facebook_dm",
                "manual_line_message",
                "in_person_visit",
            ),
            excluded_channels=(
                "automated_email",
                "bulk_dm",
                "paid_ads",
                "scraped_leads",
            ),
        )

    @staticmethod
    def of(
        *,
        profile_id: str,
        operator_name: str,
        target_market: str,
        target_location: str,
        primary_offer: str,
        starting_price: str,
        delivery_window: str,
        outreach_goal: str,
        allowed_channels: tuple[str, ...] | list[str],
        excluded_channels: tuple[str, ...] | list[str],
        metadata: dict[str, Any] | None = None,
    ) -> "OutreachLaunchProfile":
        return OutreachLaunchProfile(
            profile_id=str(profile_id),
            operator_name=str(operator_name),
            target_market=str(target_market),
            target_location=str(target_location),
            primary_offer=str(primary_offer),
            starting_price=str(starting_price),
            delivery_window=str(delivery_window),
            outreach_goal=str(outreach_goal),
            allowed_channels=tuple(str(v) for v in allowed_channels),
            excluded_channels=tuple(str(v) for v in excluded_channels),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "operator_name": self.operator_name,
            "target_market": self.target_market,
            "target_location": self.target_location,
            "primary_offer": self.primary_offer,
            "starting_price": self.starting_price,
            "delivery_window": self.delivery_window,
            "outreach_goal": self.outreach_goal,
            "allowed_channels": list(self.allowed_channels),
            "excluded_channels": list(self.excluded_channels),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OutreachAsset:
    asset_name: str
    file_name: str
    asset_type: str
    purpose: str
    required: bool
    path: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_name", str(self.asset_name))
        object.__setattr__(self, "file_name", str(self.file_name))
        object.__setattr__(self, "asset_type", str(self.asset_type))
        object.__setattr__(self, "purpose", str(self.purpose))
        object.__setattr__(self, "required", bool(self.required))
        if self.path is not None:
            object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        asset_name: str,
        file_name: str,
        asset_type: str,
        purpose: str,
        *,
        required: bool,
        path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "OutreachAsset":
        return OutreachAsset(
            asset_name=str(asset_name),
            file_name=str(file_name),
            asset_type=str(asset_type),
            purpose=str(purpose),
            required=bool(required),
            path=None if path is None else str(path),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_name": self.asset_name,
            "file_name": self.file_name,
            "asset_type": self.asset_type,
            "purpose": self.purpose,
            "required": self.required,
            "path": self.path,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OutreachReadinessCheck:
    check_name: str
    status: str
    severity: str
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        if self.status not in OUTREACH_CHECK_STATUSES:
            raise ValueError(f"invalid outreach check status: {self.status!r}")
        if self.severity not in OUTREACH_CHECK_SEVERITIES:
            raise ValueError(f"invalid outreach check severity: {self.severity!r}")
        if self.artifact_path is not None:
            object.__setattr__(self, "artifact_path", str(self.artifact_path))
        if self.error_kind is not None:
            object.__setattr__(self, "error_kind", str(self.error_kind))
        if self.error_detail is not None:
            object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str,
        *,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "OutreachReadinessCheck":
        return OutreachReadinessCheck(
            check_name=str(check_name),
            status=str(status),
            severity=str(severity),
            artifact_path=None if artifact_path is None else str(artifact_path),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "artifact_path": self.artifact_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstOutreachLaunchKitResult:
    ok: bool
    schema_version: int
    kit_id: str
    profile: OutreachLaunchProfile
    created_at: str
    output_dir: str
    manifest_path: str
    assets: tuple[OutreachAsset, ...]
    checks: tuple[OutreachReadinessCheck, ...]
    ready_for_outreach: bool
    go_no_go: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "kit_id", str(self.kit_id))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "assets", tuple(self.assets))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "ready_for_outreach", bool(self.ready_for_outreach))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        if self.go_no_go not in OUTREACH_GO_NO_GO:
            raise ValueError(f"invalid outreach go_no_go: {self.go_no_go!r}")
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "kit_id": self.kit_id,
            "profile": self.profile.to_dict(),
            "created_at": self.created_at,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "assets": [asset.to_dict() for asset in self.assets],
            "checks": [check.to_dict() for check in self.checks],
            "ready_for_outreach": self.ready_for_outreach,
            "go_no_go": self.go_no_go,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstOutreachLaunchKitError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    checks: tuple[OutreachReadinessCheck, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        checks: tuple[OutreachReadinessCheck, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstOutreachLaunchKitError":
        base = {"schema_version": FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstOutreachLaunchKitError(
            ok=False,
            schema_version=FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_step=str(failed_step),
            checks=tuple(checks),
            metadata=FrozenMap.from_mapping(base),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION",
    "OutreachLaunchProfile",
    "OutreachAsset",
    "OutreachReadinessCheck",
    "FirstOutreachLaunchKitResult",
    "FirstOutreachLaunchKitError",
)
