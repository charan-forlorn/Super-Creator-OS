
from __future__ import annotations
import hashlib, json, os, re, tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
SCHEMA_VERSION='scos-hvs.guided-pilot-intake.v1/1.0.0'; STORE_SCHEMA_VERSION='scos-hvs.guided-pilot-intake-store.v1/1.0.0'
DRAFT='DRAFT'; NEEDS_INPUT='NEEDS_INPUT'; READY_TO_CREATE='READY_TO_CREATE'; BLOCKED='BLOCKED'; CREATED='CREATED'; CREATION_OUTCOME_UNKNOWN='CREATION_OUTCOME_UNKNOWN'
LOCKED_EXTERNAL_RESTRICTIONS={'customer_notification':'NOT_AUTHORIZED','external_delivery':'NOT_AUTHORIZED','publishing':'NOT_AUTHORIZED','upload':'NOT_AUTHORIZED','deployment':'NOT_AUTHORIZED'}
RETENTION_DEFAULT='Retain customer assets for 30 days after operator handoff, then require review before deletion or extended retention.'
PRESETS={'Vertical Product Promo':('TikTok / Reels / Shorts','vertical_9_16','30s'),'Square Product Promo':('Instagram / Facebook','square_1_1','30s'),'Landscape Product Promo':('YouTube / Website','landscape_16_9','45s'),'Service Awareness Video':('Local manual handoff','landscape_16_9','60s'),'Manual Local Delivery':('Manual local delivery','operator_selected','operator_selected'),'Custom':('Custom','custom','custom')}
ALLOWED_SUFFIX={'.png','.jpg','.jpeg','.webp','.mp4','.mov','.wav','.mp3','.txt','.pdf'}; PROHIBITED={'health_data','financial_data','government_identifiers','child_information'}
def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
def sha(b): return hashlib.sha256(b if isinstance(b,bytes) else str(b).encode()).hexdigest()
def slug(s):
    x=re.sub(r'[^a-z0-9_-]+','-',str(s).lower()).strip('-_'); return (x or 'pilot')[:40]
def relto(child,parent):
    try: Path(child).resolve().relative_to(Path(parent).resolve()); return True
    except Exception: return False
def has_link_or_reparse(p:Path):
    parts=Path(p).resolve().parts
    for i in range(1,len(parts)+1):
        q=Path(*parts[:i])
        try:
            if q.exists() and q.is_symlink(): return True
            if os.name=='nt' and q.exists() and (q.stat().st_file_attributes & getattr(__import__('stat'),'FILE_ATTRIBUTE_REPARSE_POINT',0)): return True
        except OSError: return True
    return False
def inside_git(p:Path):
    p=Path(p).resolve()
    return any((q/'.git').exists() for q in (p,*p.parents))
def draft_id(title,ref=''): return 'draft-'+sha('|'.join(['draft',title.strip(),ref.strip()]))[:16]
def pilot_id(d): return 'pilot-'+slug(d.safe_project_title)+'-'+sha('|'.join([d.draft_id,d.safe_project_title,d.deadline,d.commercial_reference]))[:12]
def project_id(d): return 'project-'+sha('|'.join([d.draft_id,d.safe_project_title,d.selected_template,d.output_profile]))[:16]
def roots(pid, runtime_base='C:/Workspace/scos-paid-pilot', evidence_base='C:/Workspace/scos-paid-pilot-evidence'):
    if not re.match(r'^[a-z0-9][a-z0-9_-]{1,95}$',pid): raise ValueError('UNSAFE_PILOT_ID')
    rb=Path(runtime_base).resolve(); eb=Path(evidence_base).resolve()
    out={'runtime_root':rb/pid/'runtime','input_root':rb/pid/'input','hvs_projects_root':rb/pid/'hvs-projects','output_root':rb/pid/'output','downloads_root':rb/pid/'downloads','backup_root':rb/pid/'backup','restore_root':rb/pid/'restore','evidence_root':eb/pid}
    vals=[v.resolve() for v in out.values()]
    for v in vals:
        if has_link_or_reparse(v): raise ValueError('REPARSE_POINT_REJECTED')
        if inside_git(v): raise ValueError('GIT_REPOSITORY_ROOT_REJECTED')
    for i,a in enumerate(vals):
        for b in vals[i+1:]:
            if relto(a,b) or relto(b,a): raise ValueError('OVERLAPPING_ROOTS_REJECTED')
    return {k:str(v) for k,v in out.items()}
def generated_roots(pilot_safe_id, runtime_base='C:/Workspace/scos-paid-pilot', evidence_base='C:/Workspace/scos-paid-pilot-evidence'):
    return roots(pilot_safe_id, runtime_base, evidence_base)

@dataclass(frozen=True)
class Finding:
    field:str; status:str; message:str; why_required:str; operator_action:str; blocked_effect:str
    def to_dict(self): return dict(self.__dict__)
@dataclass(frozen=True)
class AssetReference:
    asset_id:str; safe_name:str; sha256:str; size_bytes:int; status:str; rights_required:bool; safe_reference:str
    def to_dict(self): return dict(self.__dict__)
@dataclass(frozen=True)
class GuidedIntakeDraft:
    schema_version:str=SCHEMA_VERSION; draft_id:str=''; status:str=DRAFT; safe_project_title:str=''; selected_template:str='Vertical Product Promo'; target_platform:str='TikTok / Reels / Shorts'; output_profile:str='vertical_9_16'; duration:str='30s'; deadline:str=''; commercial_reference:str=''; asset_references:tuple=(); consent_state:str='CONSENT_NOT_CONFIRMED'; consent_evidence_reference:str=''; consent_evidence_sha256:str=''; explicit_consent_confirmed:bool=False; rights_answers:dict=field(default_factory=dict); privacy_answers:dict=field(default_factory=dict); derived_classification:str='UNCLASSIFIED'; retention_policy:str=RETENTION_DEFAULT; external_action_restrictions:dict=field(default_factory=lambda:dict(LOCKED_EXTERNAL_RESTRICTIONS)); validation_findings:tuple=(); generated:dict=field(default_factory=dict); created_at:str=''; updated_at:str=''; revision:int=1; creation_idempotency_key:str=''; pilot_safe_id:str=''; project_safe_id:str=''; admission_packet_sha256:str=''
    def to_dict(self):
        d=dict(self.__dict__); d['asset_references']=[a.to_dict() for a in self.asset_references]; d['validation_findings']=[f.to_dict() for f in self.validation_findings]; return d
    @classmethod
    def from_dict(cls,d):
        assets=tuple(a if isinstance(a,AssetReference) else AssetReference(**a) for a in d.get('asset_references',[]))
        findings=tuple(f if isinstance(f,Finding) else Finding(**f) for f in d.get('validation_findings',[]))
        return cls(**{**d,'asset_references':assets,'validation_findings':findings})
def find(field,msg,act,why='Required for fail-closed paid-pilot admission.',effect='The Pilot will not be created and no assets will be processed.'): return Finding(field,'Blocked',msg,why,act,effect)
def classify(pa):
    if any(str(pa.get(k,'No'))=='Yes' for k in PROHIBITED): return 'PROHIBITED'
    if str(pa.get('identifiable_person','No'))=='Yes' or str(pa.get('voice_used','No'))=='Yes': return 'PERSONAL_DATA_REVIEW_REQUIRED'
    return 'STANDARD_COMMERCIAL'
def create_draft(**kw):
    title=str(kw.get('safe_project_title','')).strip(); tpl=str(kw.get('selected_template') or 'Vertical Product Promo'); plat,prof,dur=PRESETS.get(tpl,PRESETS['Custom']); t=now()
    d=GuidedIntakeDraft(draft_id=str(kw.get('draft_id') or draft_id(title,str(kw.get('commercial_reference','')))),safe_project_title=title,selected_template=tpl,target_platform=str(kw.get('target_platform') or plat),output_profile=str(kw.get('output_profile') or prof),duration=str(kw.get('duration') or dur),deadline=str(kw.get('deadline','')),commercial_reference=str(kw.get('commercial_reference','')),rights_answers=dict(kw.get('rights_answers') or {}),privacy_answers=dict(kw.get('privacy_answers') or {}),created_at=t,updated_at=t)
    return validate_draft(d)
def with_updates(d, **updates):
    data=d.to_dict(); data.update(updates); data['revision']=int(data.get('revision',1))+1; data['updated_at']=now(); return validate_draft(GuidedIntakeDraft.from_dict(data))
def attach_consent_evidence(d, *, safe_reference, evidence_bytes, explicit_consent_confirmed):
    return with_updates(d, consent_evidence_reference=Path(str(safe_reference)).name, consent_evidence_sha256=sha(evidence_bytes) if evidence_bytes else '', explicit_consent_confirmed=bool(explicit_consent_confirmed), consent_state='CONSENT_CONFIRMED' if explicit_consent_confirmed and evidence_bytes else 'CONSENT_NOT_CONFIRMED')
def add_asset_from_path(d, *, approved_input_root, file_path):
    root=Path(approved_input_root).resolve(); p=Path(file_path).resolve()
    if has_link_or_reparse(root) or has_link_or_reparse(p): raise ValueError('REPARSE_POINT_REJECTED')
    if not relto(p,root): raise ValueError('ASSET_OUTSIDE_APPROVED_FOLDER')
    if not p.is_file(): raise ValueError('ASSET_NOT_FILE')
    status='Unsupported file' if p.suffix.lower() not in ALLOWED_SUFFIX else ('File appears damaged' if p.stat().st_size<=0 else 'Ready')
    b=p.read_bytes(); a=AssetReference('asset-'+sha(str(p.relative_to(root)).encode()+b)[:16],p.name,sha(b),p.stat().st_size,status,True,p.name)
    return with_updates(d, asset_references=tuple([*d.asset_references,a]))
def validate_draft(d):
    fs=[]
    if not d.safe_project_title.strip(): fs.append(find('safe_project_title','Safe project title is missing.','Enter a short non-sensitive project title.'))
    if not d.deadline.strip(): fs.append(find('deadline','Deadline is missing.','Choose the pilot deadline.'))
    if not d.asset_references: fs.append(find('assets','No approved assets are attached.','Attach operator-approved input assets.'))
    if not d.consent_evidence_sha256: fs.append(find('consent_evidence','Consent evidence is missing.','Attach a redacted screenshot or signed document showing explicit approval.'))
    if d.explicit_consent_confirmed is not True: fs.append(find('explicit_consent','Explicit consent is not confirmed.','Confirm only after explicit customer approval.'))
    for k in ['asset_owner','identifiable_person','voice_used','music_used','font_policy']:
        v=str(d.rights_answers.get(k,'')).strip()
        if not v: fs.append(find(k,k.replace('_',' ').title()+' answer is missing.','Answer the guided rights question.'))
        elif v=='Not sure': fs.append(find(k,k.replace('_',' ').title()+' is uncertain.','Choose a definite answer or attach valid evidence for this gate.'))
    for k in ['health_data','financial_data','government_identifiers','child_information']:
        v=str(d.privacy_answers.get(k,'')).strip()
        if not v: fs.append(find(k,k.replace('_',' ').title()+' answer is missing.','Answer Yes, No, or Not sure.'))
        elif v=='Not sure': fs.append(find(k,k.replace('_',' ').title()+' is uncertain.','Resolve this privacy question before admission.'))
    dc=classify({**d.privacy_answers, **{k:d.rights_answers.get(k) for k in ['identifiable_person','voice_used']}})
    if dc=='PROHIBITED': fs.append(find('derived_classification','Derived classification is PROHIBITED.','Remove prohibited material or stop this intake.','SCOS does not admit prohibited paid-pilot data.','No admission packet, render, or delivery will be created.'))
    if any(a.status!='Ready' for a in d.asset_references): fs.append(find('asset_inventory','One or more assets are not ready.','Remove unsupported or damaged assets.'))
    status=READY_TO_CREATE if not fs else (BLOCKED if any(f.field=='derived_classification' for f in fs) else NEEDS_INPUT)
    pid=pilot_id(d) if d.safe_project_title else ''; prid=project_id(d) if d.safe_project_title else ''; gen=dict(d.generated)
    if pid: gen.update({'pilot_safe_id':pid,'project_safe_id':prid,'roots':roots(pid)})
    return GuidedIntakeDraft.from_dict({**d.to_dict(),'status':status,'derived_classification':dc,'validation_findings':[f.to_dict() for f in fs],'generated':gen,'pilot_safe_id':pid,'project_safe_id':prid})
class GuidedIntakeStore:
    def __init__(self,store_path): self.path=Path(store_path)
    def read(self):
        if not self.path.exists(): return {'schema_version':STORE_SCHEMA_VERSION,'drafts':{}}
        return json.loads(self.path.read_text(encoding='utf-8'))
    def write(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=self.path.name+'.',suffix='.tmp',dir=str(self.path.parent)); os.close(fd); Path(tmp).write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8'); os.replace(tmp,self.path)
    def put(self,d):
        data=self.read(); data.setdefault('drafts',{})[d.draft_id]=d.to_dict(); self.write(data); return d
    def get(self,did):
        d=self.read().get('drafts',{}).get(did); return GuidedIntakeDraft.from_dict(d) if d else None
def packet(d): return {'schema_version':SCHEMA_VERSION,'pilot_safe_id':d.pilot_safe_id,'project_safe_id':d.project_safe_id,'project':{'title':d.safe_project_title,'template':d.selected_template,'target_platform':d.target_platform,'output_profile':d.output_profile,'duration':d.duration,'deadline':d.deadline,'commercial_reference':d.commercial_reference},'assets':[a.to_dict() for a in d.asset_references],'consent':{'state':d.consent_state,'evidence_reference':d.consent_evidence_reference,'evidence_sha256':d.consent_evidence_sha256,'explicit_confirmed':d.explicit_consent_confirmed},'rights_answers':d.rights_answers,'privacy_answers':d.privacy_answers,'derived_classification':d.derived_classification,'retention_policy':d.retention_policy,'external_action_restrictions':d.external_action_restrictions,'runtime_isolation_plan':d.generated.get('roots',{}),'automation_allowed':False}
def create_pilot(store, *, draft_id, idempotency_key, runtime_base='C:/Workspace/scos-paid-pilot', evidence_base='C:/Workspace/scos-paid-pilot-evidence', recorded_at=None):
    d=store.get(draft_id)
    if not d: return {'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'}
    d=validate_draft(d)
    if d.status!=READY_TO_CREATE: store.put(d); return {'ok':False,'error_code':'ADMISSION_BLOCKED','detail':'draft is not ready','draft':d.to_dict()}
    if d.creation_idempotency_key:
        if d.creation_idempotency_key==idempotency_key: return {'ok':True,'replay':True,'draft':d.to_dict(),'pilot_safe_id':d.pilot_safe_id,'project_safe_id':d.project_safe_id,'admission_packet_sha256':d.admission_packet_sha256}
        return {'ok':False,'error_code':'CONFLICTING_REPLAY_REJECTED','detail':'idempotency key conflicts with existing creation'}
    rs=roots(d.pilot_safe_id,runtime_base,evidence_base); ev=Path(rs['evidence_root']); pend=ev/'CREATION_PENDING.json'
    if pend.exists(): return {'ok':False,'error_code':'CREATION_OUTCOME_UNKNOWN','detail':'recoverable pending reconciliation required'}
    ev.mkdir(parents=True,exist_ok=True); pend.write_text(json.dumps({'draft_id':draft_id,'idempotency_key':idempotency_key}),encoding='utf-8')
    for p in rs.values(): Path(p).mkdir(parents=True,exist_ok=True)
    pay=packet(d); pay['created_at']=recorded_at or now(); pj=json.dumps(pay,ensure_ascii=False,sort_keys=True,indent=2); psha=sha(pj)
    (ev/'admission-packet.json').write_text(pj,encoding='utf-8')
    red=json.loads(pj); red['consent']['evidence_reference']='REDACTED_SAFE_REFERENCE'; (ev/'admission-packet.redacted.json').write_text(json.dumps(red,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    sums=[]
    for n in ['admission-packet.json','admission-packet.redacted.json']: sums.append(hashlib.sha256((ev/n).read_bytes()).hexdigest()+'  '+n)
    (ev/'SHA256SUMS').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    with (ev/'audit.jsonl').open('a',encoding='utf-8',newline='\n') as fh: fh.write(json.dumps({'schema_version':SCHEMA_VERSION,'event_type':'PILOT_CREATED','draft_id':draft_id,'pilot_safe_id':d.pilot_safe_id,'packet_sha256':psha,'external_actions':LOCKED_EXTERNAL_RESTRICTIONS},ensure_ascii=False,separators=(',',':'))+'\n')
    pend.unlink()
    final=GuidedIntakeDraft.from_dict({**d.to_dict(),'status':CREATED,'creation_idempotency_key':idempotency_key,'admission_packet_sha256':psha,'generated':{**d.generated,'roots':rs,'evidence_files':['admission-packet.json','admission-packet.redacted.json','SHA256SUMS','audit.jsonl']}}); store.put(final)
    return {'ok':True,'replay':False,'draft':final.to_dict(),'pilot_safe_id':final.pilot_safe_id,'project_safe_id':final.project_safe_id,'admission_packet_sha256':psha,'next_safe_action':'Review technical evidence; no render/delivery is authorized.'}
