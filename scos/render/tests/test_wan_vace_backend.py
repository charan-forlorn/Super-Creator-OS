from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scos.render.base import RenderProfile, ShotSpec
from scos.render.generative import wan_vace_backend as wan


def _model_fixture(root: Path) -> Path:
    files = [
        'model_index.json',
        'transformer/config.json',
        'text_encoder/config.json',
        'vae/config.json',
        'tokenizer/tokenizer_config.json',
        'text_encoder/model.safetensors',
        'transformer/diffusion_pytorch_model.safetensors',
        'vae/diffusion_pytorch_model.safetensors',
    ]
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'x')
    return root


def test_backend_preflight_and_runtime_policy(monkeypatch, tmp_path):
    model = _model_fixture(tmp_path / 'model')
    py = tmp_path / 'python.exe'
    worker = tmp_path / 'wan_vace_worker.py'
    ref = tmp_path / 'ref.png'
    py.write_bytes(b'x')
    worker.write_text('# worker', encoding='utf-8')
    ref.write_bytes(b'png')
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        if '--job-file' in cmd:
            job_path = Path(cmd[cmd.index('--job-file') + 1])
            captured['job'] = json.loads(job_path.read_text(encoding='utf-8'))
            output = Path(captured['job']['output_path'])
            output.write_bytes(b'mp4')
            payload = {
                'status': 'PASS', 'scene_id': captured['job']['scene_id'],
                'output_path': str(output), 'probe': {'duration_s': 0.5625},
                'motion_score': 0.1, 'seed': captured['job']['seed'], 'frames': 9, 'fps': 16,
                'load_mode': 'cpu_offload', 'total_vram_gb': 7.93,
                'requested_width': 480, 'requested_height': 832,
                'effective_width': 272, 'effective_height': 480,
                'adaptive_resolution': True, 'resource_policy_reason': 'vram<12GB: cap-long-edge=480px',
                'peak_vram_mib': 9016.6, 'generation_seconds': 1.0,
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')
        probe = {
            'format': {'duration': '0.5625', 'size': '4'},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 272, 'height': 480, 'r_frame_rate': '16/1'}],
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(probe), stderr='')

    monkeypatch.setattr(wan.subprocess, 'run', fake_run)
    backend = wan.WanVaceBackend(model_dir=model, python_executable=py, worker_path=worker, steps=1, max_duration_s=1.0)
    assert backend.preflight()['available'] is True
    shot = ShotSpec('s', ref, None, 0.3125, prompt='test', generation_backend=wan.BACKEND_ID)
    result = backend.generate(shot, RenderProfile(), tmp_path / 'out.mp4')
    job = captured['job']
    assert job['load_mode'] == 'auto'
    assert job['adaptive_resolution'] is True
    assert result.info.find('load_mode=cpu_offload') >= 0
    assert result.info.find('effective=272x480') >= 0
