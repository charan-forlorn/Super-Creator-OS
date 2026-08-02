
from __future__ import annotations
import json, os, sys
from pathlib import Path
from scos.control_center.hvs_guided_pilot_intake import GuidedIntakeStore, add_asset_from_path, apply_brief_section, attach_consent_evidence, browser_safe_response, create_draft, create_pilot, validate_draft, with_updates
from scos.control_center.hvs_pilot_roots import resolve_task_owned_roots, RootConfigInvalid
# Browser-controlled filesystem-path fields are NEVER accepted from a request
# body. They are resolved server-side from environment only. The previous code
# forwarded store_path/evidence_base/runtime_base/approved_input_root/file_path
# directly from the browser body, which allowed a browser-selected filesystem
# path (B1/B2 root cause). Those keys below are explicitly discarded.
_BROWSER_PATH_FIELDS = (
    "store_path", "evidence_base", "runtime_base", "approved_input_root", "file_path",
)
def _server_roots():
    # Fail closed if task-owned roots are not configured server-side. This
    # guarantees no silent fallback to the shared evidence root (B1/B2).
    return resolve_task_owned_roots()
def _safe_payload(a):
    return {k: v for k, v in a.items() if k not in _BROWSER_PATH_FIELDS}
def emit(d):
    # The browser boundary is defined by the AUTHORITATIVE SERVICE, not here.
    # This CLI applies the service-owned projection; it does not implement its
    # own redaction rules and never rewrites business state (R2.1C section 7).
    print(json.dumps(browser_safe_response(d),ensure_ascii=False,sort_keys=True)); return 0
def store(roots): return GuidedIntakeStore(roots.intake_store)
def main(argv=None):
    op=(argv or sys.argv[1:] or [''])[0]
    try: a=json.loads(sys.stdin.read() or '{}')
    except Exception: return emit({'ok':False,'error_code':'REQUEST_MALFORMED','detail':'invalid json'})
    try: roots=_server_roots()
    except RootConfigInvalid as e: return emit({'ok':False,'error_code':'TASK_ROOTS_UNAVAILABLE','detail':f'{e.code}: {e.detail}'})
    safe=_safe_payload(a)
    st=store(roots)
    try:
        if op=='draft': d=create_draft(**safe); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='update':
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=with_updates(d, **dict(safe.get('updates') or {})); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='consent':
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=attach_consent_evidence(d,safe_reference=str(safe.get('safe_reference','consent-evidence.txt')),evidence_bytes=str(safe.get('evidence_text','')).encode(),explicit_consent_confirmed=bool(safe.get('explicit_consent_confirmed'))); d=validate_draft(d); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='asset':
            # Real packet-approved asset admission. asset_file is a RELATIVE reference
            # under the server-owned SCOS_PILOT_APPROVED_INPUT_ROOT (e.g.
            # "assets/product-front.jpg"). It is never an absolute or browser-
            # controlled filesystem path. Traversal is rejected (B3/B4, R2).
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            asset_file=str(safe.get('asset_file','')).strip()
            if not asset_file or asset_file.startswith('/') or asset_file.startswith('\\') or '..' in asset_file.replace('\\','/').split('/'):
                return emit({'ok':False,'error_code':'ASSET_PATH_REJECTED','detail':'asset_file must be a safe relative reference under the server-approved input root'})
            target=Path(roots.approved_input_root)/asset_file
            if not str(target.resolve()).startswith(str(Path(roots.approved_input_root).resolve())):
                return emit({'ok':False,'error_code':'ASSET_PATH_ESCAPE','detail':'asset_file escapes the approved input root'})
            d=add_asset_from_path(d,approved_input_root=str(roots.approved_input_root),file_path=str(target))
            d=validate_draft(d)  # recompute readiness after asset admission (authoritative gate)
            st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='sample-asset':
            # Test/development-only synthetic fixture. In real-packet mode this
            # MUST fail closed (B3/B4): real admission never accepts a synthetic
            # undeclared fixture. The route disables it unless mode=='test'.
            if str(safe.get('mode','')).lower()!='test':
                return emit({'ok':False,'error_code':'SAMPLE_ASSET_REJECTED_IN_REAL_MODE','detail':'synthetic fixture not allowed in real-packet admission'})
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            input_root=Path(roots.intake_runtime_base)/d.pilot_safe_id/'input'
            input_root.mkdir(parents=True,exist_ok=True)
            asset=input_root/'synthetic-product.txt'
            asset.write_text('SCOS synthetic guided-intake asset fixture (TEST ONLY)\n',encoding='utf-8')
            d=add_asset_from_path(d,approved_input_root=input_root,file_path=asset); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='brief-section':
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=apply_brief_section(d,section_id=str(safe.get('section_id','')),answers=dict(safe.get('answers') or {})); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='validate':
            d=st.get(str(safe.get('draft_id','')))
            if not d: return emit({'ok':False,'error_code':'DRAFT_NOT_FOUND','detail':'draft not found'})
            d=validate_draft(d); st.put(d); return emit({'ok':True,'draft':d.to_dict()})
        if op=='create':
            # Server-owned bases only. No browser path is accepted (B1/B2).
            return emit(create_pilot(st,draft_id=str(safe.get('draft_id','')),idempotency_key=str(safe.get('idempotency_key','')),runtime_base=str(roots.intake_runtime_base),evidence_base=str(roots.intake_evidence_base),recorded_at=safe.get('recorded_at')))
        if op=='get':
            d=st.get(str(safe.get('draft_id',''))); return emit({'ok':bool(d),'draft':d.to_dict() if d else None,'error_code':None if d else 'DRAFT_NOT_FOUND'})
    except Exception as e: return emit({'ok':False,'error_code':str(e.args[0] if e.args else type(e).__name__),'detail':'guided intake authority rejected the request'})
    return emit({'ok':False,'error_code':'UNKNOWN_OPERATION','detail':op})
if __name__=='__main__': raise SystemExit(main())
