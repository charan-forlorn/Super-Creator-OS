"""WF-1 Auto Highlight Detection Engine — offline, deterministic, additive."""
from .highlight_engine import (
    HighlightConfig, VisualEventDetector, NullVisualDetector,
    detect_highlights, fuse, detect_peaks, peaks_to_candidates, norm01, onset,
)

__all__ = [
    "HighlightConfig", "VisualEventDetector", "NullVisualDetector",
    "detect_highlights", "fuse", "detect_peaks", "peaks_to_candidates", "norm01", "onset",
]
