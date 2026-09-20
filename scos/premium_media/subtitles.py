"""Deterministic subtitle compiler for SRT/ASS and one-screen renderers."""
from __future__ import annotations

import re
from pathlib import Path

from .models import SubtitleCue, SubtitleStyle


class SubtitleError(ValueError):
    pass


_SRT_TIME = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)


def _parse_time(value: str) -> float:
    match = _SRT_TIME.fullmatch(value.strip())
    if not match:
        raise SubtitleError(f"invalid SRT timestamp: {value!r}")
    return (
        int(match["h"]) * 3600
        + int(match["m"]) * 60
        + int(match["s"])
        + int(match["ms"]) / 1000
    )


def parse_srt(text: str, *, language: str = "und") -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    blocks = re.split(r"\n\s*\n", normalized)
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            raise SubtitleError(f"malformed SRT block: {block!r}")
        timing = lines[1].split("-->")
        if len(timing) != 2:
            raise SubtitleError(f"missing SRT timing arrow: {lines[1]!r}")
        start = _parse_time(timing[0].strip())
        end = _parse_time(timing[1].strip().split(" ")[0])
        text_value = " ".join(line.strip() for line in lines[2:] if line.strip())
        if end <= start:
            raise SubtitleError(f"cue end <= start: {start}..{end}")
        cues.append(SubtitleCue(start, end, text_value, language=language))
    validate_cues(cues)
    return cues


def parse_srt_file(path: str | Path, *, language: str = "und") -> list[SubtitleCue]:
    return parse_srt(Path(path).read_text(encoding="utf-8-sig"), language=language)


def validate_cues(cues: list[SubtitleCue], *, duration_s: float | None = None) -> None:
    previous_end = -1.0
    for idx, cue in enumerate(cues):
        if cue.start_s < 0 or cue.end_s <= cue.start_s:
            raise SubtitleError(f"cue {idx}: invalid interval {cue.start_s}..{cue.end_s}")
        if cue.start_s < previous_end - 1e-6:
            raise SubtitleError(f"cue {idx}: overlaps prior cue")
        if not cue.text.strip():
            raise SubtitleError(f"cue {idx}: empty text")
        if duration_s is not None and cue.end_s > duration_s + 1e-6:
            raise SubtitleError(f"cue {idx}: ends after media duration")
        previous_end = cue.end_s


def wrap_caption(text: str, *, max_chars: int = 26) -> str:
    """Language-neutral wrapping that preserves words but breaks long tokens safely."""
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_chars:
        return text
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            pieces = [word[i:i + max_chars] for i in range(0, len(word), max_chars)]
        else:
            pieces = [word]
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= max_chars:
                current += " " + piece
            else:
                lines.append(current)
                current = piece
    if current:
        lines.append(current)
    return "\n".join(lines)


def to_ass(cues: list[SubtitleCue], *, style: SubtitleStyle | None = None) -> str:
    style = style or SubtitleStyle()
    validate_cues(cues)
    position_map = {
        "bottom_left": 1,
        "bottom_center": 2,
        "bottom_right": 3,
        "center_left": 4,
        "center": 5,
        "center_right": 6,
        "top_left": 7,
        "top_center": 8,
        "top_right": 9,
    }
    alignment = position_map.get(style.position)
    if alignment is None:
        raise SubtitleError(f"unsupported subtitle position: {style.position!r}")
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Premium,{style.font_family},{style.font_size_px},{style.primary_color},"
        f"{style.primary_color},{style.outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{style.outline_px},{style.shadow_px},{alignment},80,80,{style.margin_v},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    body: list[str] = []
    for cue in cues:
        start = _ass_time(cue.start_s)
        end = _ass_time(cue.end_s)
        wrapped = wrap_caption(cue.text, max_chars=style.max_chars_per_line)
        safe = wrapped.replace("\n", r"\N").replace("{", r"\{").replace("}", r"\}")
        body.append(f"Dialogue: 0,{start},{end},Premium,,0,0,0,,{safe}")
    return "\n".join(header + body) + "\n"


def _ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def write_ass(cues: list[SubtitleCue], path: str | Path, *, style: SubtitleStyle | None = None) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(to_ass(cues, style=style), encoding="utf-8-sig")
    return target
