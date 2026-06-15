"""Adapter: Super Creator OS  timeline_format.md  ->  video-use  edl.json (+ SRT).

NON-DESTRUCTIVE BRIDGE. Reads a Super Creator OS timeline block file and emits a
video-use-compatible EDL plus an output-timeline SRT built directly from the
on-screen Text fields (so caption burn-in needs NO ElevenLabs call).

Super Creator OS timeline line format (pipe-separated, flexible spacing):

    00:00-00:02 | Hook | Asset: a.png | Motion: Push In | Trans: None | Text: ...
    00:02-00:08 | Build | Asset: clip.mp4 | Src: 12.4-18.4 | Motion: Slow Pan | Trans: Cross Dissolve | Text: ...

Time tokens accept MM:SS or HH:MM:SS or raw seconds (e.g. 2.5).
The left "00:00-00:02" is the OUTPUT timeline position of the block.
Optional "Src: <start>-<end>" gives the IN/OUT inside a VIDEO source; if omitted
for a video asset, the source segment defaults to [0, block_duration].

Output (video-use EDL):
  - ranges[].source/start/end are SOURCE-timeline values (what render.py extracts)
  - ranges[].beat/quote/reason are preserved
  - ranges[].motion/transition/text are EXTRA keys render.py safely ignores,
    kept so Super Creator OS's motion + text plan survive the round-trip.

IMPORTANT — image assets: video-use render.py extracts from VIDEO sources. A still
image (.png/.jpg) cannot be -ss/-t extracted. Image-asset blocks are flagged
("_asset_type":"image") and reported, NOT silently emitted as broken ranges.
Convert stills to clips first (recipe printed in the report), then re-run, OR keep
using the Super Creator OS native asset-assembly path for image montages.

Usage:
    python integrations/adapter/timeline_to_edl.py <timeline.md> --assets-dir <dir> -o <edl.json>
    python integrations/adapter/timeline_to_edl.py <timeline.md> --assets-dir <dir> -o <edl.json> --grade warm_cinematic
    python integrations/adapter/timeline_to_edl.py <timeline.md> --assets-dir <dir> --srt-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

LINE_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?|\d+(?:\.\d+)?)\s*-\s*"
                     r"(\d{1,2}:\d{2}(?::\d{2})?|\d+(?:\.\d+)?)\s*\|(.+)$")


def parse_time(tok: str) -> float:
    """MM:SS | HH:MM:SS | raw seconds -> float seconds."""
    tok = tok.strip()
    if ":" not in tok:
        return float(tok)
    parts = [float(p) for p in tok.split(":")]
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    h, m, s = parts
    return h * 3600 + m * 60 + s


def parse_fields(rest: str) -> dict:
    """Parse the pipe-separated tail into a dict. First cell with no 'Key:' = beat."""
    cells = [c.strip() for c in rest.split("|") if c.strip()]
    out: dict = {}
    for idx, cell in enumerate(cells):
        m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", cell)
        if m:
            key = m.group(1).strip().lower()
            out[key] = m.group(2).strip()
        elif idx == 0:
            out["beat"] = cell
    return out


def parse_src(src: str | None) -> tuple[float, float] | None:
    if not src:
        return None
    m = re.match(r"^\s*([\d.:]+)\s*-\s*([\d.:]+)\s*$", src)
    if not m:
        return None
    return parse_time(m.group(1)), parse_time(m.group(2))


def srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Super Creator OS timeline -> video-use EDL + SRT")
    ap.add_argument("timeline", help="Path to timeline_format.md")
    ap.add_argument("--assets-dir", default=".", help="Directory holding the asset files")
    ap.add_argument("-o", "--out", default="edit/edl.json", help="EDL output path")
    ap.add_argument("--srt", default=None, help="SRT output path (default: alongside EDL as from_timeline.srt)")
    ap.add_argument("--grade", default="none", help="Grade preset or raw ffmpeg filter (default: none)")
    ap.add_argument("--srt-only", action="store_true", help="Only emit the SRT, skip the EDL")
    args = ap.parse_args()

    tl_path = Path(args.timeline)
    if not tl_path.exists():
        print(f"ERROR: timeline not found: {tl_path}", file=sys.stderr)
        return 2
    assets_dir = Path(args.assets_dir)

    blocks: list[dict] = []
    for raw in tl_path.read_text(encoding="utf-8").splitlines():
        m = LINE_RE.match(raw)
        if not m:
            continue
        out_start = parse_time(m.group(1))
        out_end = parse_time(m.group(2))
        fields = parse_fields(m.group(3))
        blocks.append({"out_start": out_start, "out_end": out_end, "fields": fields})

    if not blocks:
        print("ERROR: no timeline blocks parsed. Check the line format.", file=sys.stderr)
        return 3

    # ---- Build SRT from on-screen Text (output timeline, no ASR needed) ----
    srt_lines: list[str] = []
    n = 0
    for b in blocks:
        text = b["fields"].get("text", "").strip()
        if not text:
            continue
        n += 1
        srt_lines.append(str(n))
        srt_lines.append(f"{srt_ts(b['out_start'])} --> {srt_ts(b['out_end'])}")
        srt_lines.append(text)
        srt_lines.append("")
    srt_path = Path(args.srt) if args.srt else Path(args.out).parent / "from_timeline.srt"
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"SRT  -> {srt_path}  ({n} caption blocks from on-screen Text)")

    if args.srt_only:
        return 0

    # ---- Build EDL ----
    sources: dict[str, str] = {}
    ranges: list[dict] = []
    image_blocks = 0
    for i, b in enumerate(blocks):
        f = b["fields"]
        asset = f.get("asset", "").strip()
        if not asset:
            continue
        ext = Path(asset).suffix.lower()
        src_id = Path(asset).stem
        asset_path = (assets_dir / asset)
        sources[src_id] = str(asset_path)

        rng: dict = {
            "source": src_id,
            "beat": f.get("beat", ""),
            "quote": f.get("text", ""),
            "reason": f"auto-converted from timeline block {i}",
            # Super Creator OS extras (render.py ignores unknown keys safely):
            "motion": f.get("motion", ""),
            "transition": f.get("trans", f.get("transition", "")),
            "text": f.get("text", ""),
            "out_start": b["out_start"],
            "out_end": b["out_end"],
        }

        if ext in IMAGE_EXTS:
            image_blocks += 1
            rng["_asset_type"] = "image"
            rng["start"] = 0.0
            rng["end"] = round(b["out_end"] - b["out_start"], 3)
            rng["_warning"] = "image asset: render.py cannot -ss/-t extract a still; pre-convert to a clip first"
        else:
            src = parse_src(f.get("src"))
            if src:
                rng["start"], rng["end"] = round(src[0], 3), round(src[1], 3)
            else:
                rng["start"] = 0.0
                rng["end"] = round(b["out_end"] - b["out_start"], 3)
            rng["_asset_type"] = "video"
        ranges.append(rng)

    total = round(max(b["out_end"] for b in blocks), 3)
    edl = {
        "version": 1,
        "_generated_by": "super-creator-os/integrations/adapter/timeline_to_edl.py",
        "sources": sources,
        "ranges": ranges,
        "grade": args.grade,
        "overlays": [],
        "subtitles": str(srt_path),
        "total_duration_s": total,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EDL  -> {out_path}  ({len(ranges)} ranges, total {total}s, grade='{args.grade}')")

    if image_blocks:
        print()
        print(f"  !! {image_blocks} block(s) use STILL IMAGES. render.py extracts from VIDEO only.")
        print("     Pre-convert each still to a clip, e.g.:")
        print("       ffmpeg -loop 1 -i still.png -t <dur> -r 30 -vf scale=1080:1920,setsar=1 \\")
        print("              -c:v libx264 -pix_fmt yuv420p still_clip.mp4")
        print("     Then point the timeline Asset: at the .mp4 and re-run, OR keep the")
        print("     Super Creator OS native asset-assembly path for image montages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
