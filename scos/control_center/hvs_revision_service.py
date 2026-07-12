"""Deterministic Stage 8B revision planning; deliberately no dispatch or render."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from .hvs_delivery_lineage_service import inspect_delivery_lineage, plan_successor_version
from .hvs_delivery_lineage_models import LINEAGE_REGISTERED
from .hvs_revision_models import *
from .hvs_revision_store import append_revision_event, read_revision_events, revision_audit_path

def _digest(value: Any) -> str: return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _id(prefix: str, value: Any) -> str: return f"{prefix}-{_digest(value)[:16]}"
@dataclass(frozen=True)
class RevisionServiceResult:
    ok: bool; revision: RevisionRequest|None=None; impact: RevisionImpactAssessment|None=None; commercial: RevisionCommercialAssessment|None=None; plan: RevisionPlan|None=None; approval: RevisionApprovalRequest|None=None; authorization: RerenderAuthorizationPacket|None=None; error_code: str|None=None; error_detail: str|None=None
    def to_dict(self)->dict[str,Any]: return {"ok":self.ok,"revision":self.revision.to_dict() if self.revision else None,"impact":self.impact.to_dict() if self.impact else None,"commercial":self.commercial.to_dict() if self.commercial else None,"plan":self.plan.to_dict() if self.plan else None,"approval":self.approval.to_dict() if self.approval else None,"authorization":self.authorization.to_dict() if self.authorization else None,"automation_allowed":False,"rerender_started":False,"error_code":self.error_code,"error_detail":self.error_detail}
def _deny(code:str,detail:str)->RevisionServiceResult: return RevisionServiceResult(False,error_code=code,error_detail=detail)
def _item(d:dict[str,Any])->RevisionItem: return RevisionItem(**d)
def _request(d:dict[str,Any])->RevisionRequest: return RevisionRequest(**(d|{"revision_items":tuple(_item(x) for x in d["revision_items"])}))
def _impact(d:dict[str,Any]|None): return None if not d else RevisionImpactAssessment(**(d|{"affected_scene_ids":tuple(d["affected_scene_ids"]),"affected_asset_ids":tuple(d["affected_asset_ids"]),"affected_formats":tuple(d["affected_formats"]),"manual_checks_required":tuple(d["manual_checks_required"])}))
def _commercial(d:dict[str,Any]|None): return None if not d else RevisionCommercialAssessment(**d)
def _plan(d:dict[str,Any]|None): return None if not d else RevisionPlan(**(d|{"revision_item_ids":tuple(d["revision_item_ids"])}))
def _approval(d:dict[str,Any]|None): return None if not d else RevisionApprovalRequest(**d)
def _auth(d:dict[str,Any]|None): return None if not d else RerenderAuthorizationPacket(**d)
def _state(repo:Path,rid:str):
    current=None
    for e in read_revision_events(audit_log_path=revision_audit_path(repo)):
        if e.revision_request_id==rid: current=e.record
    return current
def _result(state:dict[str,Any])->RevisionServiceResult: return RevisionServiceResult(True,_request(state["revision"]),_impact(state.get("impact")),_commercial(state.get("commercial")),_plan(state.get("plan")),_approval(state.get("approval")),_auth(state.get("authorization")))
def _append(repo:Path,event_type:str,state:dict[str,Any],operator_id:str,at:str):
    req=state["revision"]; eid=_id("revt",{"type":event_type,"request":req["revision_request_id"],"record":state})
    append_revision_event(audit_log_path=revision_audit_path(repo),event=RevisionAuditEvent(REVISION_EVENT_SCHEMA_VERSION,eid,event_type,req["revision_request_id"],operator_id,at,state))
def create_revision_request(*,delivery_record_id:str,requested_by_id:str,operator_id:str,revision_items:tuple[RevisionItem,...],repo_root,recorded_at:str)->RevisionServiceResult:
    if not operator_id.strip() or not requested_by_id.strip(): return _deny("MISSING_OPERATOR_OR_REQUESTER","operator and requester are required")
    if not revision_items: return _deny("EMPTY_REVISION_REQUEST","revision_items are required")
    inspected=inspect_delivery_lineage(delivery_record_id=delivery_record_id,repo_root=repo_root)
    if not inspected.ok or inspected.lineage is None or inspected.lineage.lineage_status!=LINEAGE_REGISTERED: return _deny("DELIVERY_VERSION_UNKNOWN","registered delivery lineage is required")
    successor=plan_successor_version(delivery_record_id=delivery_record_id,repo_root=repo_root)
    if not successor.ok or successor.successor_plan is None: return _deny("DELIVERY_VERSION_UNKNOWN","successor version planning failed")
    lineage=inspected.lineage
    if any(item.source_artifact_sha256.lower()!=lineage.artifact_sha256.lower() for item in revision_items): return _deny("ARTIFACT_SHA_MISMATCH","revision items must bind the source artifact SHA-256")
    items=tuple(sorted(revision_items,key=lambda i:i.revision_item_id))
    if len({i.revision_item_id for i in items})!=len(items): return _deny("CONFLICTING_REVISION_ITEMS","duplicate revision items are not permitted")
    semantic={"project":lineage.project_id,"delivery":delivery_record_id,"lineage":lineage.lineage_id,"sha":lineage.artifact_sha256,"source":lineage.delivery_version_sequence,"successor":successor.successor_plan.planned_successor_version.sequence,"items":[i.to_dict() for i in items],"requester":requested_by_id}
    rid=_id("scos-hvs-revision",semantic); repo=Path(repo_root)
    existing=_state(repo,rid)
    if existing: return _result(existing)
    for event in read_revision_events(audit_log_path=revision_audit_path(repo)):
        prior=event.record.get("revision",{})
        if prior.get("delivery_record_id")==delivery_record_id and prior.get("revision_request_id")!=rid: return _deny("REVISION_REQUEST_CONFLICT","another immutable revision request already targets this delivery")
    request=RevisionRequest(REVISION_SCHEMA_VERSION,rid,lineage.project_id,lineage.recipient_label,delivery_record_id,lineage.delivery_closure_id,lineage.lineage_id,lineage.artifact_id,lineage.artifact_sha256,lineage.delivery_version_sequence,lineage.delivery_version_display,successor.successor_plan.planned_successor_version.sequence,successor.successor_plan.planned_successor_version.display,requested_by_id,operator_id,items,REVISION_REQUESTED,False,recorded_at,_digest(semantic))
    state={"revision":request.to_dict()}; _append(repo,"REVISION_REQUEST_CREATED",state,operator_id,recorded_at); return _result(state)
def start_revision_review(*,revision_request_id:str,operator_id:str,repo_root,recorded_at:str)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state: return _deny("RECORD_NOT_FOUND","revision request not found")
    if state["revision"]["status"]!=REVISION_REQUESTED: return _deny("INVALID_TRANSITION","review can start only from requested")
    state=json.loads(json.dumps(state)); state["revision"]["status"]=REVISION_UNDER_REVIEW; _append(Path(repo_root),"REVISION_REVIEW_STARTED",state,operator_id,recorded_at); return _result(state)
def assess_revision_impact(*,revision_request_id:str,operator_id:str,repo_root,recorded_at:str)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or state["revision"]["status"]!=REVISION_UNDER_REVIEW: return _deny("INVALID_TRANSITION","impact assessment requires review")
    req=_request(state["revision"]); scenes=tuple(sorted({i.scene_id or (i.target_id if i.target_type=="scene" else "") for i in req.revision_items if i.scene_id or i.target_type=="scene"})); scenes=tuple(x for x in scenes if x); assets=tuple(sorted({i.asset_id or (i.target_id if i.target_type=="asset" else "") for i in req.revision_items if i.asset_id or i.target_type=="asset"})); formats=tuple(sorted({i.format or (i.target_id if i.target_type=="format" else "") for i in req.revision_items if i.format or i.target_type=="format"})); scope="MULTI_SCENE" if len(scenes)>1 else "SINGLE_SCENE" if scenes else "MULTI_FORMAT" if len(formats)>1 else "SINGLE_FORMAT" if formats else "UNKNOWN_REQUIRES_REVIEW"; payload={"scenes":scenes,"assets":assets,"formats":formats,"scope":scope}; impact=RevisionImpactAssessment(_id("scos-hvs-impact",payload),req.revision_request_id,scope,scenes,assets,formats,("manual_quality_review",),_digest(payload)); state=json.loads(json.dumps(state)); state["revision"]["status"]=SCOPE_ASSESSED; state["impact"]=impact.to_dict(); _append(Path(repo_root),"REVISION_SCOPE_ASSESSED",state,operator_id,recorded_at); return _result(state)
def classify_revision_commercial(*,revision_request_id:str,classification:str,operator_id:str,basis:str,repo_root,recorded_at:str,amount:Any=None,currency:str|None=None,tax:Any=None,discount:Any=None)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or state["revision"]["status"]!=SCOPE_ASSESSED: return _deny("INVALID_TRANSITION","commercial classification requires scope assessment")
    if classification not in COMMERCIAL_CLASSES or not operator_id.strip() or not str(basis or "").strip(): return _deny("INVALID_COMMERCIAL_CLASSIFICATION","explicit valid classification, operator, and basis are required")
    if classification=="INCLUDED_REVISION" and not str(basis).strip(): return _deny("ENTITLEMENT_EVIDENCE_REQUIRED","included revision requires entitlement evidence")
    if amount is not None:
        if isinstance(amount,float) or not currency or tax is None or discount is None: return _deny("INVALID_MONEY","amount requires precise currency, tax, and discount")
        try: amount_text=str(Decimal(str(amount))); tax_text=str(Decimal(str(tax))); discount_text=str(Decimal(str(discount)))
        except (InvalidOperation,ValueError): return _deny("INVALID_MONEY","invalid monetary value")
    else: amount_text=tax_text=discount_text=None
    action=classification in ("CHARGEABLE_REVISION","REQUIRES_COMMERCIAL_REVIEW")
    payload={"classification":classification,"operator":operator_id,"basis":basis,"action":action,"amount":amount_text,"currency":currency,"tax":tax_text,"discount":discount_text}; commercial=RevisionCommercialAssessment(classification,operator_id,basis,action,amount_text,currency,tax_text,discount_text,_digest(payload)); state=json.loads(json.dumps(state)); state["commercial"]=commercial.to_dict(); state["revision"]["status"]=COMMERCIAL_REVIEW_REQUIRED if action else READY_FOR_APPROVAL; _append(Path(repo_root),"REVISION_COMMERCIAL_CLASSIFIED",state,operator_id,recorded_at); return _result(state)
def prepare_revision_plan(*,revision_request_id:str,operator_id:str,repo_root,recorded_at:str)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or state["revision"]["status"] not in (READY_FOR_APPROVAL,COMMERCIAL_REVIEW_REQUIRED): return _deny("INVALID_TRANSITION","plan requires complete assessment")
    if state["revision"]["status"]==COMMERCIAL_REVIEW_REQUIRED: return _deny("COMMERCIAL_REVIEW_REQUIRED","commercial review remains required")
    req=_request(state["revision"]); impact=_impact(state.get("impact")); commercial=_commercial(state.get("commercial")); payload={"request":req.revision_request_id,"impact":impact.content_hash,"commercial":commercial.content_hash,"items":[i.revision_item_id for i in req.revision_items]}; plan=RevisionPlan(_id("scos-hvs-revision-plan",payload),req.revision_request_id,_digest(payload),req.source_artifact_sha256,req.source_lineage_id,req.planned_successor_version_display,tuple(i.revision_item_id for i in req.revision_items),impact.content_hash,commercial.content_hash); state=json.loads(json.dumps(state)); state["plan"]=plan.to_dict(); _append(Path(repo_root),"REVISION_PLAN_PREPARED",state,operator_id,recorded_at); return _result(state)
def create_revision_approval_request(*,revision_request_id:str,operator_id:str,repo_root,recorded_at:str)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or not state.get("plan"): return _deny("PLAN_REQUIRED","immutable revision plan is required")
    req=_request(state["revision"]); plan=_plan(state["plan"]); com=_commercial(state["commercial"]); approval=RevisionApprovalRequest(_id("scos-hvs-rerender-approval",plan.to_dict()),req.revision_request_id,plan.revision_plan_id,plan.plan_hash,req.source_lineage_id,req.source_artifact_sha256,req.planned_successor_version_display,com.classification,operator_id); state=json.loads(json.dumps(state)); state["approval"]=approval.to_dict(); _append(Path(repo_root),"REVISION_APPROVAL_REQUESTED",state,operator_id,recorded_at); return _result(state)
def decide_revision_approval(*,revision_request_id:str,decision:str,operator_id:str,repo_root,recorded_at:str,reason:str|None=None)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or not state.get("approval") or not operator_id.strip(): return _deny("APPROVAL_REQUIRED","approval and operator are required")
    if decision not in ("APPROVE_RERENDER_PLAN","REJECT_RERENDER_PLAN") or (decision=="REJECT_RERENDER_PLAN" and not str(reason or "").strip()): return _deny("INVALID_APPROVAL_DECISION","explicit valid decision and rejection reason are required")
    state=json.loads(json.dumps(state)); state["decision"]=decision; state["decision_id"]=_id("scos-hvs-approval-decision",{"approval":state["approval"]["approval_request_id"],"decision":decision}); state["revision"]["status"]=APPROVED_FOR_RERENDER_PLANNING if decision.startswith("APPROVE") else REJECTED; _append(Path(repo_root),"REVISION_APPROVED" if decision.startswith("APPROVE") else "REVISION_REJECTED",state,operator_id,recorded_at); return _result(state)
def create_rerender_authorization(*,revision_request_id:str,operator_id:str,repo_root,recorded_at:str)->RevisionServiceResult:
    state=_state(Path(repo_root),revision_request_id)
    if not state or state.get("decision")!="APPROVE_RERENDER_PLAN": return _deny("APPROVAL_REQUIRED","approved immutable plan is required")
    req=_request(state["revision"]); plan=_plan(state["plan"]); approval=_approval(state["approval"]); auth=RerenderAuthorizationPacket(_id("scos-hvs-rerender-auth",{"plan":plan.plan_hash,"decision":state["decision_id"]}),req.revision_request_id,plan.revision_plan_id,approval.approval_request_id,state["decision_id"],req.source_artifact_sha256,req.source_lineage_id,req.planned_successor_version_display); state=json.loads(json.dumps(state)); state["authorization"]=auth.to_dict(); state["revision"]["status"]=RERENDER_AUTHORIZATION_READY; _append(Path(repo_root),"RERENDER_AUTHORIZATION_READY",state,operator_id,recorded_at); return _result(state)
