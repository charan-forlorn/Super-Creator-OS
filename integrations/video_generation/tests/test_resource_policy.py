from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'integrations' / 'video_generation'))

from resource_policy import decide_resources, select_load_mode


def test_auto_mode_uses_offload_below_12gb():
    assert select_load_mode(7.93, 'auto') == 'cpu_offload'
    assert select_load_mode(16.0, 'auto') == 'cuda'


def test_explicit_mode_wins():
    assert select_load_mode(7.93, 'cuda') == 'cuda'
    assert select_load_mode(16.0, 'cpu_offload') == 'cpu_offload'


def test_8gb_policy_caps_long_edge_to_480():
    d = decide_resources(7.93, 832, 480, 'auto', True)
    assert d.load_mode == 'cpu_offload'
    assert d.effective_width == 480
    assert d.effective_height == 272
    assert d.adaptive_resolution is True


def test_native_resolution_for_larger_vram():
    d = decide_resources(16.0, 832, 480, 'auto', True)
    assert d.effective_width == 832
    assert d.effective_height == 480
    assert d.adaptive_resolution is False


def test_adaptation_can_be_disabled():
    d = decide_resources(7.93, 832, 480, 'auto', False)
    assert d.effective_width == 832
    assert d.effective_height == 480
    assert d.adaptive_resolution is False
