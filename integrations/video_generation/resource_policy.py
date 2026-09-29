"""Deterministic hardware-aware policy for local video generation workers."""
from __future__ import annotations

from dataclasses import dataclass

AUTO_CPU_OFFLOAD_VRAM_GB = 12.0
SAFE_LONG_EDGE_VRAM_GB = 12.0
SAFE_LONG_EDGE_PX_8GB = 480
MIN_DIMENSION_PX = 128
DIMENSION_ALIGNMENT = 16

@dataclass(frozen=True)
class ResourceDecision:
    load_mode: str
    requested_width: int
    requested_height: int
    effective_width: int
    effective_height: int
    adaptive_resolution: bool
    reason: str

def select_load_mode(total_vram_gb: float, requested: str = "auto") -> str:
    requested = requested.lower().strip()
    if requested not in {"auto", "cuda", "cpu_offload"}:
        raise ValueError("load_mode must be auto, cuda, or cpu_offload")
    if requested != "auto":
        return requested
    return "cpu_offload" if total_vram_gb < AUTO_CPU_OFFLOAD_VRAM_GB else "cuda"

def _align(value: float) -> int:
    raw = max(MIN_DIMENSION_PX, int(round(value)))
    return max(DIMENSION_ALIGNMENT, int(round(raw / DIMENSION_ALIGNMENT)) * DIMENSION_ALIGNMENT)

def decide_resources(
    total_vram_gb: float,
    width: int,
    height: int,
    requested_load_mode: str = "auto",
    adaptive_resolution: bool = True,
) -> ResourceDecision:
    load_mode = select_load_mode(total_vram_gb, requested_load_mode)
    effective_width, effective_height = int(width), int(height)
    adapted = False
    reason = "native-resolution"
    if adaptive_resolution and total_vram_gb < SAFE_LONG_EDGE_VRAM_GB and max(effective_width, effective_height) > SAFE_LONG_EDGE_PX_8GB:
        scale = SAFE_LONG_EDGE_PX_8GB / float(max(effective_width, effective_height))
        effective_width = _align(effective_width * scale)
        effective_height = _align(effective_height * scale)
        adapted = True
        reason = f"vram<{SAFE_LONG_EDGE_VRAM_GB:.0f}GB: cap-long-edge={SAFE_LONG_EDGE_PX_8GB}px"
    return ResourceDecision(
        load_mode=load_mode,
        requested_width=int(width),
        requested_height=int(height),
        effective_width=effective_width,
        effective_height=effective_height,
        adaptive_resolution=adapted,
        reason=reason,
    )
