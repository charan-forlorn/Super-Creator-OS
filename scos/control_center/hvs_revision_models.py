"""Stage 8B local-only revision planning contracts; no HVS execution."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

REVISION_SCHEMA_VERSION = "scos-hvs.revision-rerender.v1/1.0.0"
REVISION_EVENT_SCHEMA_VERSION = "scos-hvs.revision-event.v1/1.0.0"
REVISION_REQUESTED = "REVISION_REQUESTED"
REVISION_UNDER_REVIEW = "REVISION_UNDER_REVIEW"
SCOPE_ASSESSED = "SCOPE_ASSESSED"
COMMERCIAL_REVIEW_REQUIRED = "COMMERCIAL_REVIEW_REQUIRED"
READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
APPROVED_FOR_RERENDER_PLANNING = "APPROVED_FOR_RERENDER_PLANNING"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
RERENDER_AUTHORIZATION_READY = "RERENDER_AUTHORIZATION_READY"
CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
ITEM_CATEGORIES = ("TEXT_CHANGE", "CAPTION_CHANGE", "TIMING_CHANGE", "ASSET_REPLACEMENT", "AUDIO_CHANGE", "MUSIC_CHANGE", "VOICE_CHANGE", "LAYOUT_CHANGE", "BRANDING_CHANGE", "FORMAT_CHANGE", "DURATION_CHANGE", "COMPLIANCE_CHANGE", "TECHNICAL_CORRECTION", "OTHER")
COMMERCIAL_CLASSES = ("INCLUDED_REVISION", "CHARGEABLE_REVISION", "WARRANTY_CORRECTION", "INTERNAL_CORRECTION", "REQUIRES_COMMERCIAL_REVIEW", "REJECTED_OUT_OF_SCOPE")
SCOPES = ("METADATA_ONLY", "SINGLE_SCENE", "MULTI_SCENE", "FULL_TIMELINE", "SINGLE_FORMAT", "MULTI_FORMAT", "FULL_REBUILD", "UNKNOWN_REQUIRES_REVIEW")
EVENT_TYPES = ("REVISION_REQUEST_CREATED", "REVISION_REVIEW_STARTED", "REVISION_SCOPE_ASSESSED", "REVISION_COMMERCIAL_CLASSIFIED", "REVISION_PLAN_PREPARED", "REVISION_APPROVAL_REQUESTED", "REVISION_APPROVED", "REVISION_REJECTED", "RERENDER_AUTHORIZATION_READY")

def _hash(prefix: str, value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(text.encode()).hexdigest()[:16]}"

def _safe_id(field: str, value: str) -> str:
    text = str(value or "").strip()
    if not text or any(token in text.lower() for token in ("..", "\\", "/", "://", ";", "|", "$", "`")):
        raise ValueError(f"{field} must be a safe logical identifier")
    return text

@dataclass(frozen=True)
class RevisionItem:
    revision_item_id: str; category: str; description: str; target_type: str; target_id: str
    priority: str; acceptance_requirement: str; requested_by_id: str; source_artifact_sha256: str
    scene_id: str | None = None; asset_id: str | None = None; format: str | None = None
    timeline_start: int | None = None; timeline_end: int | None = None
    @classmethod
    def create(cls, **data: Any) -> "RevisionItem":
        category = str(data["category"]).strip().upper()
        if category not in ITEM_CATEGORIES: raise ValueError("unsupported revision item category")
        description = str(data.get("description") or "").strip()
        if not description: raise ValueError("revision item description is required")
        target_type = _safe_id("target_type", data["target_type"]); target_id = _safe_id("target_id", data["target_id"])
        for key in ("scene_id", "asset_id", "format"):
            if data.get(key) is not None: _safe_id(key, data[key])
        payload = {k: data.get(k) for k in ("category", "description", "target_type", "target_id", "scene_id", "asset_id", "format", "timeline_start", "timeline_end", "priority", "acceptance_requirement", "requested_by_id", "source_artifact_sha256")}
        payload.update({"category": category, "description": description, "target_type": target_type, "target_id": target_id})
        return cls(revision_item_id=_hash("scos-hvs-revision-item", payload), **payload)
    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class RevisionRequest:
    schema_version: str; revision_request_id: str; project_id: str | None; recipient_label: str | None
    delivery_record_id: str; delivery_closure_id: str; source_lineage_id: str; source_artifact_id: str; source_artifact_sha256: str
    source_delivery_version_sequence: int; source_delivery_version_display: str; planned_successor_version_sequence: int; planned_successor_version_display: str
    requested_by_id: str; created_by_operator_id: str; revision_items: tuple[RevisionItem, ...]; status: str; automation_allowed: bool; created_at: str; deterministic_content_hash: str
    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__); data["revision_items"] = [item.to_dict() for item in self.revision_items]; return data

@dataclass(frozen=True)
class RevisionImpactAssessment:
    assessment_id: str; revision_request_id: str; scope: str; affected_scene_ids: tuple[str, ...]; affected_asset_ids: tuple[str, ...]; affected_formats: tuple[str, ...]; manual_checks_required: tuple[str, ...]; content_hash: str
    def to_dict(self) -> dict[str, Any]: return {**self.__dict__, "affected_scene_ids": list(self.affected_scene_ids), "affected_asset_ids": list(self.affected_asset_ids), "affected_formats": list(self.affected_formats), "manual_checks_required": list(self.manual_checks_required)}

@dataclass(frozen=True)
class RevisionCommercialAssessment:
    classification: str; operator_id: str; basis: str; commercial_action_required: bool; amount: str | None; currency: str | None; tax: str | None; discount: str | None; content_hash: str
    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class RevisionPlan:
    revision_plan_id: str; revision_request_id: str; plan_hash: str; source_artifact_sha256: str; source_lineage_id: str; planned_successor_version_display: str; revision_item_ids: tuple[str, ...]; impact_hash: str; commercial_hash: str; supersession_status: str = "NOT_YET_SUPERSEDED"; source_artifact_preserved: bool = True; no_overwrite_required: bool = True; automation_allowed: bool = False; rerender_started: bool = False
    def to_dict(self) -> dict[str, Any]: return {**self.__dict__, "revision_item_ids": list(self.revision_item_ids)}

@dataclass(frozen=True)
class RevisionApprovalRequest:
    approval_request_id: str; revision_request_id: str; revision_plan_id: str; revision_plan_hash: str; source_lineage_id: str; source_artifact_sha256: str; planned_successor_version_display: str; commercial_classification: str; operator_id: str
    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class RerenderAuthorizationPacket:
    rerender_authorization_id: str; revision_request_id: str; revision_plan_id: str; approval_request_id: str; approval_decision_id: str; source_artifact_sha256: str; source_lineage_id: str; planned_successor_version_display: str; manual_dispatch_required: bool = True; automation_allowed: bool = False; rerender_started: bool = False; source_artifact_preserved: bool = True; no_overwrite_required: bool = True; supersession_status: str = "NOT_YET_SUPERSEDED"
    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class RevisionAuditEvent:
    schema_version: str; event_id: str; event_type: str; revision_request_id: str; operator_id: str; recorded_at: str; record: dict[str, Any]
    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)
