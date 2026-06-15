"""vu.py — Super Creator OS ↔ video-use engine launcher (Windows-safe entry point).

Why this exists: the vendored video-use helpers print Unicode (→, ✓, …) which
crashes on Windows' default cp1252 console (UnicodeEncodeError). This launcher
forces UTF-8 I/O before dispatching, so callers never have to remember to set
PYTHONUTF8=1. It also keeps the engine helpers importable as siblings.

Usage (from the super-creator-os project root):
    python integrations/video-use/vu.py transcribe       <video> [args...]
    python integrations/video-use/vu.py transcribe_batch  <videos_dir> [args...]
    python integrations/video-use/vu.py pack_transcripts  --edit-dir <dir>
    python integrations/video-use/vu.py timeline_view      <video> <start> <end>
    python integrations/video-use/vu.py render             <edl.json> -o <out> [--preview]
    python integrations/video-use/vu.py grade              <in> -o <out>

This is a thin shim: it sets encoding, then runs helpers/<name>.py with the
remaining argv unchanged. All original video-use flags pass straight through.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent / "engine" / "helpers"
VALID = {"transcribe", "transcribe_batch", "pack_transcripts",
         "timeline_view", "render", "grade"}


def _force_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # py3.7+
        except Exception:
            pass


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(__doc__)
        print("tools:", ", ".join(sorted(VALID)))
        return 0
    tool = sys.argv[1]
    if tool not in VALID:
        print(f"ERROR: unknown tool '{tool}'. Valid: {', '.join(sorted(VALID))}", file=sys.stderr)
        return 2

    _force_utf8()
    target = HELPERS / f"{tool}.py"
    if not target.exists():
        print(f"ERROR: helper not found: {target}", file=sys.stderr)
        return 2

    # Let the helper import its siblings (transcribe_batch imports transcribe;
    # render imports grade) by putting helpers/ on sys.path.
    sys.path.insert(0, str(HELPERS))
    # Hand the helper a clean argv: argv[0]=helper, then its own args.
    sys.argv = [str(target)] + sys.argv[2:]
    runpy.run_path(str(target), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
