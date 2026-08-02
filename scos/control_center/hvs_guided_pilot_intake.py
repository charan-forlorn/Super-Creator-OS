
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
# --- Cohort 10K plain-language Brief Studio (authoritative, deterministic) ---
# The browser is a collector only. Every readiness state, recommended default and
# resolved output profile below is computed here, inside the sole authoritative
# writer, and published read-only under draft.generated['brief'].
BRIEF_SCHEMA_VERSION='scos-hvs.guided-brief-studio.v1/1.0.0'
UNSURE='ยังไม่แน่ใจ'
RIGHTS_KEYS=('asset_owner','identifiable_person','voice_used','music_used','font_policy')
PRIVACY_KEYS=('health_data','financial_data','government_identifiers','child_information')
BRIEF_SECTION_IDS=('goal','audience','message','style','channel','assets','schedule','rights')
# Required plain-language answers per section. 'schedule' is satisfied by the
# draft-level deadline; 'assets' and 'rights' are satisfied by the existing
# fail-closed asset / rights / privacy authority, never by a free-text answer.
BRIEF_REQUIRED={'goal':('goal',),'audience':('audience',),'message':('main_point',),'style':(),'channel':('channel',),'assets':(),'schedule':(),'rights':()}
BRIEF_TEXT={
 'goal':('เป้าหมายของงาน','ระบบต้องรู้ว่าคุณอยากได้งานแบบไหน จึงจะเตรียมโครงงานให้ถูกต้อง','เลือกเป้าหมายจากตัวเลือก หรือพิมพ์อธิบายด้วยคำพูดของคุณเอง'),
 'audience':('กลุ่มผู้ชม','ถ้าไม่รู้ว่าใครจะดู เนื้อหาจะจับใจคนดูไม่ได้','บอกสั้น ๆ ว่าคนดูคือใคร'),
 'message':('ข้อความหลัก','ข้อความหลักคือสิ่งที่คนดูต้องจำให้ได้','เขียนประโยคเดียวที่อยากให้คนดูจำ'),
 'style':('สไตล์และอารมณ์','สไตล์ช่วยให้งานดูเป็นแบรนด์เดียวกัน','เลือกสไตล์ที่ใกล้เคียงที่สุด ถ้ายังไม่แน่ใจ ระบบจะแนะนำให้'),
 'channel':('ช่องทางและรูปแบบ','ช่องทางกำหนดสัดส่วนภาพและความยาวที่เหมาะสม','เลือกช่องทางที่จะนำไปใช้'),
 'assets':('ไฟล์และวัตถุดิบ','ถ้าไฟล์ยังไม่พร้อม งานจะเริ่มไม่ได้','เพิ่มไฟล์ที่ผู้ดูแลอนุมัติแล้ว แล้วกดตรวจสอบไฟล์อีกครั้ง'),
 'schedule':('กำหนดเวลาและเงื่อนไข','กำหนดเวลาช่วยให้วางลำดับงานได้','เลือกวันที่ต้องการให้งานเสร็จ'),
 'rights':('สิทธิ์ ความยินยอม และความเป็นส่วนตัว','คำตอบเรื่องสิทธิ์และความเป็นส่วนตัวต้องชัดเจน เพื่อไม่ให้เกิดปัญหาทางกฎหมายภายหลัง','ตอบให้ชัดเจนทุกข้อ ถ้ายังไม่แน่ใจ ให้ตรวจสอบกับเจ้าของงานก่อน'),
}
# Creative (non-safety) recommended defaults. These are RECOMMENDATIONS: they are
# always labelled as such in the projection and never silently applied to a
# rights, consent or privacy answer.
BRIEF_CREATIVE_DEFAULTS={'style_tone':'เรียบง่ายและน่าเชื่อถือ','channel':'TikTok / Reels / Shorts'}
BRIEF_CHANNEL_MAP={
 'TikTok / Reels / Shorts':('Vertical Product Promo','TikTok / Reels / Shorts','vertical_9_16','30s'),
 'Facebook / Instagram feed':('Square Product Promo','Instagram / Facebook','square_1_1','30s'),
 'YouTube':('Landscape Product Promo','YouTube / Website','landscape_16_9','45s'),
 'เว็บไซต์':('Landscape Product Promo','YouTube / Website','landscape_16_9','45s'),
 'นำเสนอในร้าน':('Service Awareness Video','Local manual handoff','landscape_16_9','60s'),
}
BRIEF_ANSWER_KEYS=('goal','goal_detail','audience','audience_problem','audience_feeling','audience_next_step','main_point','offer','call_to_action','required_wording','avoid_wording','style_tone','style_colors','style_font_feel','style_reference','style_avoid','channel','asset_notes','deadline','campaign_date','max_duration','revision_note','special_instruction')

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
def roots(pid, runtime_base, evidence_base):
    # R2.1C: runtime_base/evidence_base are REQUIRED. The historical hard-coded
    # defaults ('C:/Workspace/scos-paid-pilot[-evidence]') were a reachable
    # shared-root fallback: any caller that omitted them silently resolved onto
    # the shared operator roots. There is now exactly one root authority
    # (hvs_pilot_roots.resolve_task_owned_roots) and no in-service default.
    if not str(runtime_base or '').strip() or not str(evidence_base or '').strip():
        raise ValueError('TASK_OWNED_ROOTS_REQUIRED')
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
def generated_roots(pilot_safe_id, runtime_base, evidence_base):
    return roots(pilot_safe_id, runtime_base, evidence_base)

# --- R2.1C browser-boundary redaction (service-owned, single authority) ------
# The authoritative service - not the CLI and not the route - decides what may
# cross the browser boundary. Filesystem roots are trusted SERVER-side execution
# state: they remain in the stored draft and in the on-disk admission packet so
# server-side processing and R2.2 semantics are unchanged, but they are never
# projected to the browser.
BROWSER_REDACTED_GENERATED_KEYS = ('roots',)
_ABS_PATH_RE = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\|/[^/\s])')
REDACTED_SERVER_PATH = 'REDACTED_SERVER_PATH'

def _is_abs_path_str(v):
    return isinstance(v, str) and bool(_ABS_PATH_RE.match(v))

def _redact_paths(obj):
    """Defense in depth: replace any absolute path anywhere in a browser payload."""
    if isinstance(obj, dict): return {k: _redact_paths(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_redact_paths(v) for v in obj]
    return REDACTED_SERVER_PATH if _is_abs_path_str(obj) else obj

def browser_safe_generated(gen):
    """Strip server root identity from the 'generated' projection.

    Root identity is replaced by a bounded, non-path status so the browser can
    still tell that isolated task-owned storage was provisioned.
    """
    src = dict(gen or {})
    out = {k: v for k, v in src.items() if k not in BROWSER_REDACTED_GENERATED_KEYS}
    if src.get('roots'):
        out['runtime_isolation'] = {'status': 'SERVER_MANAGED', 'root_count': len(src['roots'])}
    return _redact_paths(out)

def browser_safe_draft(d):
    """Browser-facing projection of an authoritative draft. Never contains paths."""
    data = d.to_dict() if hasattr(d, 'to_dict') else dict(d or {})
    data['generated'] = browser_safe_generated(data.get('generated'))
    return _redact_paths(data)

def browser_safe_response(res):
    """Browser-facing projection of a service response envelope."""
    out = dict(res or {})
    if isinstance(out.get('draft'), dict): out['draft'] = browser_safe_draft(out['draft'])
    return _redact_paths(out)

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
    schema_version:str=SCHEMA_VERSION; draft_id:str=''; status:str=DRAFT; safe_project_title:str=''; selected_template:str='Vertical Product Promo'; target_platform:str='TikTok / Reels / Shorts'; output_profile:str='vertical_9_16'; duration:str='30s'; deadline:str=''; commercial_reference:str=''; asset_references:tuple=(); consent_state:str='CONSENT_NOT_CONFIRMED'; consent_evidence_reference:str=''; consent_evidence_sha256:str=''; explicit_consent_confirmed:bool=False; rights_answers:dict=field(default_factory=dict); privacy_answers:dict=field(default_factory=dict); derived_classification:str='UNCLASSIFIED'; retention_policy:str=RETENTION_DEFAULT; external_action_restrictions:dict=field(default_factory=lambda:dict(LOCKED_EXTERNAL_RESTRICTIONS)); validation_findings:tuple=(); generated:dict=field(default_factory=dict); created_at:str=''; updated_at:str=''; revision:int=1; creation_idempotency_key:str=''; pilot_safe_id:str=''; project_safe_id:str=''; admission_packet_sha256:str=''; brief_mode:bool=False; brief_answers:dict=field(default_factory=dict)
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
def brief_recommendations(ba):
    """Deterministic, clearly-labelled creative recommendations.

    Only non-safety creative fields may receive a recommended default. Rights,
    consent and privacy answers are never defaulted here: they stay fail-closed.
    """
    out={}
    for k,v in BRIEF_CREATIVE_DEFAULTS.items():
        cur=str(ba.get(k,'')).strip()
        if not cur or cur==UNSURE: out[k]={'field':k,'value':v,'label':'คำแนะนำของระบบ (ยังเปลี่ยนได้)','reason':'คุณยังไม่แน่ใจ ระบบจึงเลือกค่าที่ปลอดภัยที่สุดให้ก่อน และคุณเปลี่ยนได้ตลอด'}
    return out
def brief_effective(ba):
    """Answers after applying labelled creative recommendations."""
    eff=dict(ba)
    for k,rec in brief_recommendations(ba).items(): eff[k]=rec['value']
    return eff
def brief_channel_resolution(ba):
    tpl,plat,prof,dur=BRIEF_CHANNEL_MAP[BRIEF_CREATIVE_DEFAULTS['channel']]
    ch=str(brief_effective(ba).get('channel','')).strip()
    if ch in BRIEF_CHANNEL_MAP: tpl,plat,prof,dur=BRIEF_CHANNEL_MAP[ch]
    return {'selected_template':tpl,'target_platform':plat,'output_profile':prof,'duration':dur}
def apply_brief_section(d, *, section_id, answers):
    """Authoritative write of one plain-language brief section.

    The browser sends plain answers only. Every derived technical field
    (template, platform, output profile, duration, project title, deadline) is
    resolved here, never in the browser.
    """
    sid=str(section_id).strip()
    if sid not in BRIEF_SECTION_IDS: raise ValueError('UNKNOWN_BRIEF_SECTION')
    incoming={k:('' if v is None else str(v)) for k,v in dict(answers or {}).items() if k in BRIEF_ANSWER_KEYS}
    ba={**dict(d.brief_answers), **incoming}
    upd={'brief_mode':True,'brief_answers':ba}
    title=(ba.get('goal_detail') or ba.get('goal') or '').strip()
    if title: upd['safe_project_title']=title[:80]
    if str(ba.get('deadline','')).strip(): upd['deadline']=str(ba['deadline']).strip()
    upd.update(brief_channel_resolution(ba))
    if not str(d.commercial_reference or '').strip(): upd['commercial_reference']='brief-studio'
    return with_updates(d, **upd)
def brief_projection(d, findings):
    """Browser-safe projection of authoritative state. No paths, no schema names."""
    ba=dict(d.brief_answers); eff=brief_effective(ba); recs=brief_recommendations(ba)
    fields={f.field for f in findings}
    rights_blocked=bool(fields & set(RIGHTS_KEYS) or {'consent_evidence','explicit_consent'} & fields)
    privacy_blocked=bool(fields & set(PRIVACY_KEYS) or 'derived_classification' in fields)
    assets_blocked=bool({'assets','asset_inventory'} & fields)
    sections=[]
    for sid in BRIEF_SECTION_IDS:
        heading,why,how=BRIEF_TEXT[sid]
        missing=[k for k in BRIEF_REQUIRED[sid] if not str(eff.get(k,'')).strip() or str(eff.get(k,'')).strip()==UNSURE]
        state='READY'; blocking=False; detail=''
        if sid=='rights' and (rights_blocked or privacy_blocked):
            state='BLOCKED_FOR_PRIVACY' if privacy_blocked and not rights_blocked else 'BLOCKED_FOR_RIGHTS'; blocking=True
            detail='ยังมีคำตอบเรื่องสิทธิ์หรือความเป็นส่วนตัวที่ไม่ชัดเจน ระบบจะไม่สร้างโปรเจกต์จนกว่าจะตอบให้ชัดเจน'
        elif sid=='assets' and assets_blocked:
            state='BLOCKED_FOR_ASSETS'; blocking=True; detail='ไฟล์ที่จำเป็นยังไม่พร้อม'
        elif sid=='schedule' and not str(d.deadline or '').strip():
            state='NEEDS_INFORMATION'; blocking=True; detail='ยังไม่ได้เลือกวันที่ต้องการให้งานเสร็จ'
        elif missing:
            state='NEEDS_INFORMATION'; blocking=True; detail='ยังตอบไม่ครบในส่วนนี้'
        sections.append({'id':sid,'heading':heading,'state':state,'blocking':blocking,'why_it_matters':why,'how_to_resolve':how,'detail':detail,'recommended':[recs[k] for k in recs if k in BRIEF_REQUIRED.get(sid,()) or (sid=='style' and k=='style_tone') or (sid=='channel' and k=='channel')]})
    ready=sum(1 for s in sections if s['state']=='READY')
    assets={'available':sum(1 for a in d.asset_references if a.status=='Ready'),'needs_review':sum(1 for a in d.asset_references if a.status not in ('Ready','Unsupported file')),'unsupported':sum(1 for a in d.asset_references if a.status=='Unsupported file'),'names':[a.safe_name for a in d.asset_references],'missing':0 if d.asset_references else 1}
    overall='CREATED' if d.status==CREATED else ('READY' if d.status==READY_TO_CREATE else next((s['state'] for s in sections if s['blocking'] and s['state'].startswith('BLOCKED')),'NEEDS_INFORMATION'))
    return {'schema_version':BRIEF_SCHEMA_VERSION,'sections':sections,'ready_count':ready,'total_count':len(sections),'readiness_label':'พร้อมแล้ว %d จาก %d ส่วน'%(ready,len(sections)),'overall':overall,'answers':eff,'raw_answers':ba,'recommendations':list(recs.values()),'assets':assets,'resolved_output':brief_channel_resolution(ba),'will_not_do':['ระบบจะไม่ส่งข้อความหาลูกค้าให้อัตโนมัติ','ระบบจะไม่เผยแพร่หรืออัปโหลดงานให้อัตโนมัติ','ระบบจะไม่ส่งข้อมูลออกนอกเครื่องนี้','ระบบจะไม่เรนเดอร์วิดีโอจริงจนกว่าผู้ดูแลจะสั่ง']}
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
    pid=pilot_id(d) if d.safe_project_title else ''; prid=project_id(d) if d.safe_project_title else ''
    gen=dict(d.generated)
    # R2.1C: roots are NEVER derived here. validate_draft is reachable from the
    # browser-facing draft/asset/consent/validate operations; calling the root
    # authority with defaults previously leaked the shared operator roots into
    # the response. Roots are set exactly once, by create_pilot, from the
    # server-owned task-root contract, and are only preserved here if present.
    if pid: gen.update({'pilot_safe_id':pid,'project_safe_id':prid})
    nd=GuidedIntakeDraft.from_dict({**d.to_dict(),'status':status,'derived_classification':dc,'validation_findings':[f.to_dict() for f in fs],'generated':gen,'pilot_safe_id':pid,'project_safe_id':prid})
    if nd.brief_mode: gen=dict(gen); gen['brief']=brief_projection(nd,fs); nd=GuidedIntakeDraft.from_dict({**nd.to_dict(),'generated':gen})
    return nd
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
def create_pilot(store, *, draft_id, idempotency_key, runtime_base, evidence_base, recorded_at=None):
    # R2.1C: runtime_base/evidence_base are REQUIRED (no shared-root default).
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
    final=GuidedIntakeDraft.from_dict({**d.to_dict(),'status':CREATED,'creation_idempotency_key':idempotency_key,'admission_packet_sha256':psha,'generated':{**d.generated,'roots':rs,'evidence_files':['admission-packet.json','admission-packet.redacted.json','SHA256SUMS','audit.jsonl']}})
    if final.brief_mode: final=GuidedIntakeDraft.from_dict({**final.to_dict(),'generated':{**final.generated,'brief':brief_projection(final,())}})
    store.put(final)
    return {'ok':True,'replay':False,'draft':final.to_dict(),'pilot_safe_id':final.pilot_safe_id,'project_safe_id':final.project_safe_id,'admission_packet_sha256':psha,'next_safe_action':'Review technical evidence; no render/delivery is authorized.'}
