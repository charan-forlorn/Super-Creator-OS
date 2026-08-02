
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import pytest
from scos.control_center.hvs_guided_pilot_intake import (
    BRIEF_SECTION_IDS,
    GuidedIntakeStore,
    add_asset_from_path,
    apply_brief_section,
    attach_consent_evidence,
    brief_recommendations,
    create_draft,
    create_pilot,
    validate_draft,
    with_updates,
)
from scos.control_center.hvs_guided_pilot_intake_cli import main as cli_main

# R2.1C test-harness contract repair.
#
# The browser-controlled 'store_path' request field was removed from the CLI:
# task-owned roots are now resolved server-side from the canonical SCOS_PILOT_*
# environment contract (fail-closed when absent). These tests previously drove
# the CLI through that removed field, so they exercised an authority the
# product no longer offers.
#
# This fixture sanitizes any inherited SCOS_PILOT_* value first, then provisions
# only pytest-owned OS-temp roots outside SCOS and HVS. Test payloads carry no
# filesystem path at all. Harness-only: no product assertion is weakened.
SCOS_PILOT_ENV_PREFIX = 'SCOS_PILOT_'
STALE_SENTINEL_VAR = SCOS_PILOT_ENV_PREFIX + 'STALE_SENTINEL'


@pytest.fixture
def stale_inherited_env():
    """Opt-in marker: request this to have a stale non-canonical SCOS_PILOT_*
    variable exported before the autouse sanitizer runs (see _task_owned_roots).
    """
    return STALE_SENTINEL_VAR


@pytest.fixture(autouse=True)
def _task_owned_roots(tmp_path, monkeypatch, request):
    # A stale NON-canonical variable is injected first when the test opts in, so
    # the sanitizer below must actively delete it (overwriting the canonical
    # names alone cannot clear it). This keeps the sanitizer mutation-resistant.
    if 'stale_inherited_env' in request.fixturenames:
        monkeypatch.setenv(STALE_SENTINEL_VAR, 'C:/Workspace/scos-paid-pilot-evidence')
    for key in [k for k in os.environ if k.startswith(SCOS_PILOT_ENV_PREFIX)]:
        monkeypatch.delenv(key, raising=False)
    roots = tmp_path / 'task-owned'
    for name, target in {
        'INTAKE_STORE': roots / 'intake-store.json',
        'PACKET_ADMISSION_STORE': roots / 'adm.json',
        'AUDIT_STORE': roots / 'audit.jsonl',
        'AUTHORIZATION_STORE': roots / 'auth.json',
        'MATERIALIZATION_STATE': roots / 'mat.json',
        'HVS_PROJECTS_ROOT': roots / 'hvs-projects',
        'RENDER_READINESS_STATE': roots / 'rr.json',
        'OUTPUT_ROOT': roots / 'output',
        'APPROVED_INPUT_ROOT': roots / 'approved-input',
        'INTAKE_RUNTIME_BASE': roots / 'runtime',
        'INTAKE_EVIDENCE_BASE': roots / 'evidence',
    }.items():
        monkeypatch.setenv(SCOS_PILOT_ENV_PREFIX + name, str(target))
    return roots


def _stdin(monkeypatch, payload):
    """Drive the CLI with a browser-shaped payload that carries no path."""
    assert not [k for k in payload if k in {
        'store_path', 'runtime_base', 'evidence_base', 'approved_input_root', 'file_path',
    }], 'test payload must not contain a browser-controlled filesystem path'
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))

# Cohort 10K — focused coverage for the plain-language Brief Studio authority.
# Synthetic data only. No real customer information is used anywhere.

def _rights(**over):
    base = dict(asset_owner='Owned', identifiable_person='No', voice_used='Not used', music_used='Not used', font_policy='Licensed')
    base.update(over)
    return base

def _privacy(**over):
    base = dict(health_data='No', financial_data='No', government_identifiers='No', child_information='No')
    base.update(over)
    return base

def _brief_draft():
    d = create_draft(safe_project_title='Synthetic Brief', deadline='', rights_answers=_rights(), privacy_answers=_privacy())
    d = apply_brief_section(d, section_id='goal', answers={'goal': 'วิดีโอโปรโมตสินค้า'})
    d = apply_brief_section(d, section_id='audience', answers={'audience': 'ลูกค้าประจำของร้าน'})
    d = apply_brief_section(d, section_id='message', answers={'main_point': 'สูตรใหม่ หวานน้อย'})
    d = apply_brief_section(d, section_id='channel', answers={'channel': 'TikTok / Reels / Shorts'})
    d = apply_brief_section(d, section_id='schedule', answers={'deadline': '2026-08-15'})
    return d

def _ready_brief(tmp_path: Path):
    d = _brief_draft()
    inp = tmp_path / 'input'
    inp.mkdir(exist_ok=True)
    asset = inp / 'synthetic.png'
    asset.write_bytes(b'synthetic asset')
    d = add_asset_from_path(d, approved_input_root=inp, file_path=asset)
    d = attach_consent_evidence(d, safe_reference='redacted-consent.txt', evidence_bytes=b'explicit approval', explicit_consent_confirmed=True)
    return validate_draft(d)


def test_brief_sections_readiness_and_plain_projection():
    d = _brief_draft()
    b = d.generated['brief']
    assert [s['id'] for s in b['sections']] == list(BRIEF_SECTION_IDS)
    assert b['total_count'] == 8
    assert b['readiness_label'].startswith('พร้อมแล้ว')
    # every section carries plain-language guidance, never a schema name
    for s in b['sections']:
        assert s['heading'] and s['why_it_matters'] and s['how_to_resolve']
    blob = json.dumps(b, ensure_ascii=False)
    assert 'C:\\' not in blob and 'C:/' not in blob
    assert 'output_profile' not in blob.replace('"output_profile"', '')  # only inside resolved_output key
    assert d.brief_mode is True


def test_channel_choice_resolves_authoritative_output_profile():
    d = apply_brief_section(_brief_draft(), section_id='channel', answers={'channel': 'YouTube'})
    assert d.selected_template == 'Landscape Product Promo'
    assert d.output_profile == 'landscape_16_9'
    assert d.duration == '45s'
    assert d.generated['brief']['resolved_output']['target_platform'] == 'YouTube / Website'


def test_creative_not_sure_produces_labelled_recommendation_and_does_not_block():
    d = apply_brief_section(_brief_draft(), section_id='style', answers={'style_tone': 'ยังไม่แน่ใจ'})
    recs = {r['field']: r for r in d.generated['brief']['recommendations']}
    assert recs['style_tone']['value'] == 'เรียบง่ายและน่าเชื่อถือ'
    assert 'คำแนะนำของระบบ' in recs['style_tone']['label']
    style = next(s for s in d.generated['brief']['sections'] if s['id'] == 'style')
    assert style['state'] == 'READY' and style['blocking'] is False
    # a creative recommendation never fabricates a rights or privacy answer
    assert 'asset_owner' not in recs and 'health_data' not in recs
    assert brief_recommendations({'style_tone': 'พรีเมียม', 'channel': 'YouTube'}) == {}


def test_rights_not_sure_blocks_creation_fail_closed(tmp_path):
    d = _ready_brief(tmp_path)
    assert d.status == 'READY_TO_CREATE'
    blocked = with_updates(d, rights_answers=_rights(music_used='Not sure'))
    assert blocked.status != 'READY_TO_CREATE'
    section = next(s for s in blocked.generated['brief']['sections'] if s['id'] == 'rights')
    assert section['state'] == 'BLOCKED_FOR_RIGHTS' and section['blocking'] is True
    assert blocked.generated['brief']['overall'] == 'BLOCKED_FOR_RIGHTS'


def test_privacy_not_sure_and_prohibited_block_creation(tmp_path):
    d = _ready_brief(tmp_path)
    unsure = with_updates(d, privacy_answers=_privacy(child_information='Not sure'))
    assert unsure.status != 'READY_TO_CREATE'
    assert next(s for s in unsure.generated['brief']['sections'] if s['id'] == 'rights')['state'] == 'BLOCKED_FOR_PRIVACY'
    prohibited = with_updates(d, privacy_answers=_privacy(health_data='Yes'))
    assert prohibited.status == 'BLOCKED' and prohibited.derived_classification == 'PROHIBITED'


def test_missing_required_section_and_missing_assets_are_reported(tmp_path):
    d = create_draft(safe_project_title='x', deadline='', rights_answers=_rights(), privacy_answers=_privacy())
    d = apply_brief_section(d, section_id='goal', answers={'goal': ''})
    b = d.generated['brief']
    goal = next(s for s in b['sections'] if s['id'] == 'goal')
    assert goal['state'] == 'NEEDS_INFORMATION' and goal['blocking'] is True
    assets = next(s for s in b['sections'] if s['id'] == 'assets')
    assert assets['state'] == 'BLOCKED_FOR_ASSETS'
    assert b['assets']['available'] == 0
    schedule = next(s for s in b['sections'] if s['id'] == 'schedule')
    assert schedule['state'] == 'NEEDS_INFORMATION'


def test_unknown_brief_section_is_rejected():
    with pytest.raises(ValueError, match='UNKNOWN_BRIEF_SECTION'):
        apply_brief_section(_brief_draft(), section_id='internal_schema', answers={})


def test_atomic_creation_replay_conflict_and_redaction_for_brief_drafts(tmp_path):
    d = _ready_brief(tmp_path)
    st = GuidedIntakeStore(tmp_path / 'store.json')
    st.put(d)
    out = create_pilot(st, draft_id=d.draft_id, idempotency_key='brief-1', runtime_base=tmp_path / 'rt', evidence_base=tmp_path / 'ev')
    assert out['ok'] and out['draft']['status'] == 'CREATED'
    assert out['draft']['generated']['brief']['overall'] == 'CREATED'
    ev = Path(out['draft']['generated']['roots']['evidence_root'])
    assert 'explicit approval' not in (ev / 'admission-packet.redacted.json').read_text(encoding='utf-8')
    replay = create_pilot(st, draft_id=d.draft_id, idempotency_key='brief-1', runtime_base=tmp_path / 'rt', evidence_base=tmp_path / 'ev')
    assert replay['ok'] and replay['replay'] and replay['pilot_safe_id'] == out['pilot_safe_id']
    conflict = create_pilot(st, draft_id=d.draft_id, idempotency_key='brief-2', runtime_base=tmp_path / 'rt', evidence_base=tmp_path / 'ev')
    assert not conflict['ok'] and conflict['error_code'] == 'CONFLICTING_REPLAY_REJECTED'


def test_creation_outcome_unknown_is_preserved_for_brief_drafts(tmp_path):
    d = _ready_brief(tmp_path)
    st = GuidedIntakeStore(tmp_path / 'store.json')
    st.put(d)
    ev = tmp_path / 'ev' / d.pilot_safe_id
    ev.mkdir(parents=True)
    (ev / 'CREATION_PENDING.json').write_text('{}', encoding='utf-8')
    out = create_pilot(st, draft_id=d.draft_id, idempotency_key='brief-1', runtime_base=tmp_path / 'rt', evidence_base=tmp_path / 'ev')
    assert not out['ok'] and out['error_code'] == 'CREATION_OUTCOME_UNKNOWN'


def test_cli_brief_section_roundtrip_and_resume(tmp_path, monkeypatch, capsys):
    _stdin(monkeypatch, {'safe_project_title': 'Synthetic Brief', 'deadline': '2026-08-15', 'rights_answers': _rights(), 'privacy_answers': _privacy()})
    cli_main(['draft'])
    did = json.loads(capsys.readouterr().out)['draft']['draft_id']

    _stdin(monkeypatch, {'draft_id': did, 'section_id': 'goal', 'answers': {'goal': 'วิดีโอให้ความรู้'}})
    cli_main(['brief-section'])
    saved = json.loads(capsys.readouterr().out)
    assert saved['ok'] and saved['draft']['brief_answers']['goal'] == 'วิดีโอให้ความรู้'

    _stdin(monkeypatch, {'draft_id': did})
    cli_main(['get'])
    resumed = json.loads(capsys.readouterr().out)
    assert resumed['ok'] and resumed['draft']['brief_answers']['goal'] == 'วิดีโอให้ความรู้'
    assert resumed['draft']['generated']['brief']['readiness_label'].startswith('พร้อมแล้ว')

    _stdin(monkeypatch, {'draft_id': 'missing-draft', 'section_id': 'goal', 'answers': {}})
    cli_main(['brief-section'])
    assert json.loads(capsys.readouterr().out)['error_code'] == 'DRAFT_NOT_FOUND'


def test_cli_brief_section_rejects_unknown_section_without_leaking(tmp_path, monkeypatch, capsys):
    _stdin(monkeypatch, {'safe_project_title': 'Synthetic Brief', 'deadline': '2026-08-15', 'rights_answers': _rights(), 'privacy_answers': _privacy()})
    cli_main(['draft'])
    did = json.loads(capsys.readouterr().out)['draft']['draft_id']
    _stdin(monkeypatch, {'draft_id': did, 'section_id': 'not-a-section', 'answers': {}})
    cli_main(['brief-section'])
    out = json.loads(capsys.readouterr().out)
    assert out['ok'] is False and out['error_code'] == 'UNKNOWN_BRIEF_SECTION'
    assert 'Traceback' not in json.dumps(out) and 'C:\\' not in json.dumps(out)


def test_cli_brief_harness_ignores_contaminated_parent_environment(tmp_path, monkeypatch, capsys, request):
    """Contamination regression (R2.1C section 7).

    Proves the autouse fixture DELETES inherited SCOS_PILOT_* state rather than
    merely overwriting the canonical names. A stale non-canonical variable
    (e.g. a renamed or deprecated root) must not survive into the child
    resolver, so this asserts on a sentinel the fixture never sets itself.
    """
    # Sentinel injected before the autouse fixture runs for the nested item.
    assert SCOS_PILOT_ENV_PREFIX + 'STALE_SENTINEL' not in os.environ, (
        'stale non-canonical SCOS_PILOT_* variable survived environment sanitization'
    )
    present = {k: v for k, v in os.environ.items() if k.startswith(SCOS_PILOT_ENV_PREFIX)}
    assert present, 'task-owned roots were not provisioned'
    owned = str(tmp_path)
    for key, value in present.items():
        assert Path(value).is_absolute(), f'{key} is not absolute'
        assert value.startswith(owned), f'{key} escaped the pytest-owned root'

    _stdin(monkeypatch, {'safe_project_title': 'Synthetic Brief', 'deadline': '2026-08-15', 'rights_answers': _rights(), 'privacy_answers': _privacy()})
    cli_main(['draft'])
    out = json.loads(capsys.readouterr().out)
    assert out['ok']
    assert 'roots' not in out['draft']['generated']
    assert 'C:\\' not in json.dumps(out) and 'C:/' not in json.dumps(out)
    assert Path(os.environ[SCOS_PILOT_ENV_PREFIX + 'INTAKE_STORE']).exists()


def test_harness_sanitizer_removes_stale_non_canonical_variables(stale_inherited_env):
    """The sanitizer must delete, not merely overwrite (mutation-resistant).

    ``stale_inherited_env`` exports a stale non-canonical variable BEFORE the
    autouse fixture runs. If the fixture's delenv loop is removed, the variable
    survives and this fails.
    """
    assert stale_inherited_env not in os.environ
