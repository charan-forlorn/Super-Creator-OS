"""WF-2 Auto Short Generator — offline single-pass ffmpeg renderer. Additive."""
from .short_generator import (
    ShortOptions, PRESETS, render_short, select_candidate,
    build_video_chain, action_center_frac,
)

__all__ = ["ShortOptions", "PRESETS", "render_short", "select_candidate",
           "build_video_chain", "action_center_frac"]
