"""CLI entrypoint for SCOS Premium Single-Screen renders."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scos.premium_media.brand import BrandKitError, resolve_brand_profile
from scos.premium_media.creative_graph import graph_from_props
from scos.premium_media.safe_zone import LayoutBox, validate_layout
from scos.premium_media.models import AudioRole, AudioStem, PremiumRenderProfile
from scos.premium_media.pipeline import finalize_video
from scos.premium_media.render_router import RenderJob, RenderRouter
from scos.premium_media.subtitles import parse_srt_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "premium_media" / "render_profiles.json"
REMOTION_DIR = ROOT / "work" / "production" / "remotion-wireframe-v4"


def load_profile(name: str) -> PremiumRenderProfile:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    values = raw["profiles"][name]
    return PremiumRenderProfile(**values)


def parse_stem(spec: str, role: AudioRole) -> AudioStem:
    pieces = spec.split("|")
    if len(pieces) < 1 or not pieces[0].strip():
        raise ValueError(f"invalid audio stem: {spec!r}")
    gain = float(pieces[1]) if len(pieces) > 1 and pieces[1] else 0.0
    start = float(pieces[2]) if len(pieces) > 2 and pieces[2] else 0.0
    return AudioStem(
        asset_id=str(Path(pieces[0]).resolve()),
        role=role,
        gain_db=gain,
        start_s=start,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="ad_vertical_1080")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--props", type=Path)
    source.add_argument("--graph", type=Path)
    ap.add_argument("--composition", default="PremiumSingleScreen")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--subtitle", type=Path, default=None)
    ap.add_argument("--voice", type=str, default=None, help="path[|gain_db][|start_s]")
    ap.add_argument("--music", type=str, default=None, help="path[|gain_db][|start_s]")
    ap.add_argument("--sfx", action="append", default=[], help="path[|gain_db][|start_s]")
    args = ap.parse_args()

    profile = load_profile(args.profile)
    source_path = args.graph or args.props
    raw_props = json.loads(source_path.read_text(encoding="utf-8"))
    graph = graph_from_props(raw_props)
    try:
        brand = resolve_brand_profile(ROOT, graph.brand_kit_id)
    except BrandKitError as exc:
        raise SystemExit(f"brand kit resolution failed: {exc}") from exc

    safe_errors = validate_layout(
        width=profile.width,
        height=profile.height,
        boxes=(
            LayoutBox("primary_content", 70, 180, profile.width - 70, 1650),
            LayoutBox("caption_region", 78, 1450, profile.width - 78, 1750),
        ),
    )
    if safe_errors:
        raise SystemExit("safe-zone preflight failed: " + "; ".join(safe_errors))

    props = graph.to_remotion_props()
    if brand is not None:
        props["brand"] = {
            "brand_kit_id": brand.brand_kit_id,
            "name": brand.name,
            "colors": {
                "primary": brand.primary,
                "secondary": brand.secondary,
                "accent": brand.accent,
                "neutrals": list(brand.neutrals),
            },
            "fonts": {"heading": brand.heading_font, "body": brand.body_font},
            "logo_asset_ref": brand.logo_asset_ref,
            "cta": {"label": brand.cta_label, "target": brand.cta_target},
        }
    if "duration_s" not in props:
        props["duration_s"] = 30.0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    base = args.output.with_name(args.output.stem + ".render.mp4")
    job = RenderJob(
        project_dir=REMOTION_DIR,
        entrypoint="src/index.jsx",
        composition_id=args.composition,
        props=props,
        output_path=base,
        profile=profile,
    )
    rendered = RenderRouter().render_remotion(job)

    stems: list[AudioStem] = []
    if args.voice:
        stems.append(parse_stem(args.voice, AudioRole.VOICE))
    if args.music:
        stems.append(parse_stem(args.music, AudioRole.MUSIC))
    for spec in args.sfx:
        stems.append(parse_stem(spec, AudioRole.SFX))

    cues = parse_srt_file(args.subtitle, language="und") if args.subtitle else []
    report = finalize_video(
        rendered,
        args.output,
        profile,
        audio_stems=stems,
        subtitles=cues,
        production_metadata={
            "graph_version": graph.graph_version,
            "graph_fingerprint": graph.fingerprint(),
            "project_id": graph.brief.project_id,
            "loop_run_id": graph.brief.loop_run_id,
            "brand_kit_id": graph.brand_kit_id,
            "brand_fingerprint": brand.fingerprint() if brand is not None else None,
            "style_profile_id": graph.style_profile_id,
            "master_profile_id": graph.master_profile_id,
            "delivery_profile_ids": list(graph.delivery_profile_ids),
        },
    )
    print(json.dumps({
        "passed": report.passed,
        "output": str(args.output.resolve()),
        "profile": profile.name,
        "duration_s": report.probe.duration_s if report.probe else None,
        "width": report.probe.width if report.probe else None,
        "height": report.probe.height if report.probe else None,
        "fps": report.probe.fps if report.probe else None,
        "integrated_lufs": report.loudness.integrated_lufs if report.loudness else None,
        "true_peak_db": report.loudness.true_peak_db if report.loudness else None,
        "human_publish_gate": "NOT_APPROVED",
        "external_publish": "NOT_PERFORMED",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
