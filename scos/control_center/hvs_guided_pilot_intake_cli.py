
from __future__ import annotations
import json, sys
from pathlib import Path
from scos.control_center.hvs_guided_pilot_intake import GuidedIntakeStore, add_asset_from_path, attach_consent_evidence, create_draft, create_pilot, validate_draft, with_updates
def emit(d): print(json.dumps(d,ensure_ascii=False,sort_keys=True)); return 0
def store(a): return GuidedIntakeStore(a.get('store_path') or str(Path(a.get('evidence_base') or 'C:/Workspace/scos-paid-pilot-evidence')/'_guided-intake-store-v1.json'))
def main(argv=None):
    op=(argv or sys.argv[1:] or [''])[0]
    try: a=json.loads(sys.stdin.read() or '{}')
    except Exception: return emit({'ok':False,'error_code':'REQUEST_MALFORMED','detail':'invalid json'})
    st=store(a)
    try:
        if op=='draft': d=create_draft(**a); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='update':
            d=st.get(str(a.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=with_updates(d, **dict(a.get('updates') or {})); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='consent':
            d=st.get(str(a.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=attach_consent_evidence(d,safe_reference=str(a.get('safe_reference','consent-evidence.txt')),evidence_bytes=str(a.get('evidence_text','')).encode(),explicit_consent_confirmed=bool(a.get('explicit_consent_confirmed'))); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='asset':
            d=st.get(str(a.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=add_asset_from_path(d,approved_input_root=a.get('approved_input_root',''),file_path=a.get('file_path','')); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='sample-asset':
            d=st.get(str(a.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            input_root=Path(d.generated.get('roots',{}).get('input_root') or (Path(a.get('runtime_base') or 'C:/Workspace/scos-paid-pilot')/d.pilot_safe_id/'input'))
            input_root.mkdir(parents=True,exist_ok=True)
            asset=input_root/'synthetic-product.txt'
            asset.write_text('SCOS synthetic guided-intake asset fixture\n',encoding='utf-8')
            d=add_asset_from_path(d,approved_input_root=input_root,file_path=asset); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='validate':
            d=st.get(str(a.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=validate_draft(d); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='create': return emit(create_pilot(st,draft_id=str(a.get('draft_id','')),idempotency_key=str(a.get('idempotency_key','')),runtime_base=a.get('runtime_base') or 'C:/Workspace/scos-paid-pilot',evidence_base=a.get('evidence_base') or 'C:/Workspace/scos-paid-pilot-evidence',recorded_at=a.get('recorded_at')))
        if op=='get':
            d=st.get(str(a.get('draft_id',''))); return emit({'ok':bool(d),'draft':d.to_dict() if d else None,'error_code':None if d else 'DRAFT_NOT_FOUND'})
    except Exception as e: return emit({'ok':False,'error_code':str(e.args[0] if e.args else type(e).__name__),'detail':'guided intake authority rejected the request'})
    return emit({'ok':False,'error_code':'UNKNOWN_OPERATION','detail':op})
if __name__=='__main__': raise SystemExit(main())
