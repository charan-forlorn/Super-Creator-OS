
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pytest
from scos.control_center.hvs_guided_pilot_intake import GuidedIntakeStore, add_asset_from_path, attach_consent_evidence, create_draft, create_pilot, generated_roots, validate_draft, with_updates

def _answers():
    return dict(asset_owner='Owned', identifiable_person='No', voice_used='Not used', music_used='Not used', font_policy='Licensed')
def _privacy(): return dict(health_data='No', financial_data='No', government_identifiers='No', child_information='No')
def _ready(tmp_path: Path):
    d=create_draft(safe_project_title='Synthetic Product Promo', selected_template='Vertical Product Promo', deadline='2026-08-15', rights_answers=_answers(), privacy_answers=_privacy())
    inp=tmp_path/'input'; inp.mkdir(); asset=inp/'synthetic.png'; asset.write_bytes(b'synthetic asset')
    d=add_asset_from_path(d, approved_input_root=inp, file_path=asset)
    d=attach_consent_evidence(d, safe_reference='redacted-consent.txt', evidence_bytes=b'explicit approval', explicit_consent_confirmed=True)
    return validate_draft(d)

def test_safe_id_and_root_generation_outside_repo(tmp_path):
    d=_ready(tmp_path); assert d.status=='READY_TO_CREATE'; assert d.pilot_safe_id.startswith('pilot-synthetic-product-promo-'); assert d.project_safe_id.startswith('project-')
    roots=generated_roots(d.pilot_safe_id, tmp_path/'runtime-base', tmp_path/'evidence-base')
    assert set(roots) >= {'runtime_root','input_root','hvs_projects_root','output_root','downloads_root','backup_root','restore_root','evidence_root'}
    assert all(Path(v).is_absolute() for v in roots.values())

def test_path_boundary_and_reparse_rejection(tmp_path):
    d=create_draft(safe_project_title='x', deadline='2026-08-15', rights_answers=_answers(), privacy_answers=_privacy())
    root=tmp_path/'input'; root.mkdir(); outside=tmp_path/'outside.png'; outside.write_bytes(b'x')
    with pytest.raises(ValueError, match='ASSET_OUTSIDE_APPROVED_FOLDER'): add_asset_from_path(d, approved_input_root=root, file_path=outside)
    link=root/'link.png'
    try: link.symlink_to(outside)
    except OSError: pytest.skip('symlink unavailable')
    with pytest.raises(ValueError, match='REPARSE_POINT_REJECTED'): add_asset_from_path(d, approved_input_root=root, file_path=link)

def test_consent_ambiguous_rights_privacy_and_prohibited_block(tmp_path):
    d=create_draft(safe_project_title='x', deadline='2026-08-15', rights_answers={**_answers(),'music_used':'Not sure'}, privacy_answers=_privacy())
    assert any(f.field=='music_used' for f in d.validation_findings)
    d=create_draft(safe_project_title='x', deadline='2026-08-15', rights_answers=_answers(), privacy_answers={**_privacy(),'health_data':'Yes'})
    assert d.status=='BLOCKED'; assert d.derived_classification=='PROHIBITED'
    d=_ready(tmp_path); d=with_updates(d, explicit_consent_confirmed=False)
    assert d.status!='READY_TO_CREATE'; assert any(f.field=='explicit_consent' for f in d.validation_findings)

def test_atomic_packet_redaction_sha_sums_replay_and_conflict(tmp_path):
    d=_ready(tmp_path); st=GuidedIntakeStore(tmp_path/'store.json'); st.put(d)
    out=create_pilot(st,draft_id=d.draft_id,idempotency_key='key-1',runtime_base=tmp_path/'runtime',evidence_base=tmp_path/'evidence',recorded_at='2026-07-29T00:00:00Z')
    assert out['ok']; ev=Path(out['draft']['generated']['roots']['evidence_root'])
    packet=ev/'admission-packet.json'; red=ev/'admission-packet.redacted.json'; sums=ev/'SHA256SUMS'; audit=ev/'audit.jsonl'
    assert packet.is_file() and red.is_file() and sums.is_file() and audit.is_file()
    assert 'explicit approval' not in red.read_text(encoding='utf-8')
    lines=sums.read_text(encoding='utf-8').splitlines(); assert hashlib.sha256(packet.read_bytes()).hexdigest() in lines[0]
    replay=create_pilot(st,draft_id=d.draft_id,idempotency_key='key-1',runtime_base=tmp_path/'runtime',evidence_base=tmp_path/'evidence')
    assert replay['ok'] and replay['replay'] and replay['pilot_safe_id']==out['pilot_safe_id']
    conflict=create_pilot(st,draft_id=d.draft_id,idempotency_key='key-2',runtime_base=tmp_path/'runtime',evidence_base=tmp_path/'evidence')
    assert not conflict['ok'] and conflict['error_code']=='CONFLICTING_REPLAY_REJECTED'

def test_crash_recovery_pending_boundary(tmp_path):
    d=_ready(tmp_path); st=GuidedIntakeStore(tmp_path/'store.json'); st.put(d)
    ev=tmp_path/'evidence'/d.pilot_safe_id; ev.mkdir(parents=True); (ev/'CREATION_PENDING.json').write_text('{}')
    out=create_pilot(st,draft_id=d.draft_id,idempotency_key='key-1',runtime_base=tmp_path/'runtime',evidence_base=tmp_path/'evidence')
    assert not out['ok'] and out['error_code']=='CREATION_OUTCOME_UNKNOWN'
