"""Stage 8L approval-gated HVS project initialization models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id


PROJECT_INITIALIZATION_SCHEMA_VERSION = "scos-hvs.project-initialization-stage8l.v1/1.0.0"
PROJECT_INITIALIZATION_EVENT_SCHEMA_VERSION = "scos-hvs.project-initialization-event.v1/1.0.0"
HVS_INITIALIZATION_CONTRACT_SCHEMA_VERSION = "hvs.project-initialization.v1"
HVS_INITIALIZATION_CONTRACT_NAME = "scos-hvs.project-initialization"
HVS_INITIALIZATION_CONTRACT_VERSION = "1"

INITIALIZATION_PREPARED = "HVS_PROJECT_INITIALIZATION_PREPARED"
INITIALIZATION_VERIFIED = "HVS_PROJECT_INITIALIZED_AND_VERIFIED"
INITIALIZATION_CONFLICT = "PROJECT_INITIALIZATION_CONFLICT"
INITIALIZATION_REJECTED = "PROJECT_INITIALIZATION_REJECTED"

EVT_PROJECT_INITIALIZATION_PREPARED = "PROJECT_INITIALIZATION_PREPARED"
EVT_PROJECT_INITIALIZATION_VERIFIED = "PROJECT_INITIALIZATION_VERIFIED"
EVT_PROJECT_INITIALIZATION_CONFLICT = "PROJECT_INITIALIZATION_CONFLICT"


def content_hash(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8l-content", {"payload": canonical_json(payload)})


def initialization_contract_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8l-contract", payload)


def hvs_project_id_for_authorization(production_kickoff_authorization_id: str) -> str:
    return stable_id(
        "hvs8l",
        {"production_kickoff_authorization_id": str(production_kickoff_authorization_id)},
    )


@dataclass(frozen=True)
class ProductionSceneInput:
    scene_id: str
    duration_ms: int
    intent: str
    visual_description: str
    text_overlay: str
    asset_refs: tuple[dict[str, Any], ...] = ()
    captions: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "duration_ms": self.duration_ms,
            "intent": self.intent,
            "visual_description": self.visual_description,
            "text_overlay": self.text_overlay,
            "asset_refs": [dict(item) for item in self.asset_refs],
            "captions": [dict(item) for item in self.captions],
        }


@dataclass(frozen=True)
class ProductionInitializationInput:
    title: str
    language: str
    scenes: tuple[ProductionSceneInput, ...]
    width: int = 1080
    height: int = 1920
    fps: int = 30
    selected_preset: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "language": self.language,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "selected_preset": self.selected_preset,
            "scenes": [scene.to_dict() for scene in self.scenes],
        }


@dataclass(frozen=True)
class ProductionInitializationContract:
    schema_version: str
    initialization_contract_id: str
    production_kickoff_authorization_id: str
    engagement_activation_id: str
    scos_project_id: str
    hvs_project_id: str
    title: str
    language: str
    stage2_payload_hash: str
    deterministic_content_hash: str
    hvs_initialization_contract: dict[str, Any]
    asset_materialization_authorized: bool = False
    assets_copied: bool = False
    render_authorized: bool = False
    render_started: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "initialization_contract_id": self.initialization_contract_id,
            "production_kickoff_authorization_id": self.production_kickoff_authorization_id,
            "engagement_activation_id": self.engagement_activation_id,
            "scos_project_id": self.scos_project_id,
            "hvs_project_id": self.hvs_project_id,
            "title": self.title,
            "language": self.language,
            "stage2_payload_hash": self.stage2_payload_hash,
            "deterministic_content_hash": self.deterministic_content_hash,
            "hvs_initialization_contract": self.hvs_initialization_contract,
            "asset_materialization_authorized": False,
            "assets_copied": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class HVSProjectInitializationEvidence:
    schema_version: str
    initialization_contract_id: str
    production_kickoff_authorization_id: str
    engagement_activation_id: str
    scos_project_id: str
    hvs_project_id: str
    stage2_payload_hash: str
    initialization_status: str
    hvs_initialize_exit_code: int | None
    hvs_inspect_exit_code: int | None
    project_created: bool
    identical_replay: bool
    project_verified: bool
    semantic_comparison_passed: bool
    correlation_id: str
    hvs_project_relative_path: str
    error_code: str | None = None
    error_detail: str | None = None
    asset_materialization_authorized: bool = False
    assets_copied: bool = False
    render_authorized: bool = False
    render_started: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__) | {
            "asset_materialization_authorized": False,
            "assets_copied": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class HVSProjectInitializationEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class HVSProjectInitializationResult:
    ok: bool
    contract: ProductionInitializationContract | None = None
    evidence: HVSProjectInitializationEvidence | None = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "contract": self.contract.to_dict() if self.contract else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "duplicate_of": self.duplicate_of,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "blockers": list(self.blockers),
            "asset_materialization_authorized": False,
            "assets_copied": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


def contract_from_dict(data: dict[str, Any]) -> ProductionInitializationContract:
    return ProductionInitializationContract(**data)


def evidence_from_dict(data: dict[str, Any]) -> HVSProjectInitializationEvidence:
    return HVSProjectInitializationEvidence(**data)
