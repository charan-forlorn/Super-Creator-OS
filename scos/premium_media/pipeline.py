"""Premium single-screen finishing pipeline with two-pass loudness mastering."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

from .audio import build_mix_plan
from .models import AudioStem, MediaAsset, PremiumRenderProfile, SubtitleCue, SubtitleStyle
from .qc import QCError, QCReport, analyze_loudness, validate_render
from .rights import validate_manifest_for_publish
from .subtitles import write_ass


class PremiumPipelineError(RuntimeError):
    pass


def _run(args: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise PremiumPipelineError((proc.stderr or proc.stdout)[-5000:])
    return proc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ass_filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:")


def _render_stem_mix(
    stems: Sequence[AudioStem],
    profile: PremiumRenderProfile,
    work_dir: Path,
) -> tuple[Path, object]:
    plan = build_mix_plan(
        stems,
        profile,
        input_index_offset=0,
        include_loudnorm=False,
    )
    mixed = work_dir / "premix_48k.wav"
    _run([
        "ffmpeg", "-y",
        *plan.input_args,
        "-filter_complex", plan.filter_complex,
        "-map", plan.output_label,
        "-c:a", "pcm_s24le",
        "-ar", str(profile.sample_rate),
        "-ac", "2",
        str(mixed),
    ])
    loudness = analyze_loudness(
        mixed,
        target_lufs=profile.target_lufs,
        tp=profile.max_true_peak_db,
    )
    if (
        loudness.integrated_lufs is None
        or loudness.true_peak_db is None
        or loudness.input_thresh is None
        or loudness.target_offset is None
    ):
        raise PremiumPipelineError(
            "two-pass loudness analysis did not produce all required measurements"
        )
    return mixed, loudness


def _render_source_audio_mix(
    source: Path,
    profile: PremiumRenderProfile,
    work_dir: Path,
) -> tuple[Path, object]:
    mixed = work_dir / "source_audio_48k.wav"
    _run([
        "ffmpeg", "-y", "-i", str(source),
        "-map", "0:a:0",
        "-c:a", "pcm_s24le",
        "-ar", str(profile.sample_rate),
        "-ac", "2",
        str(mixed),
    ])
    loudness = analyze_loudness(
        mixed,
        target_lufs=profile.target_lufs,
        tp=profile.max_true_peak_db,
    )
    if (
        loudness.integrated_lufs is None
        or loudness.true_peak_db is None
        or loudness.input_thresh is None
        or loudness.target_offset is None
    ):
        raise PremiumPipelineError(
            "source audio loudness analysis did not produce all required measurements"
        )
    return mixed, loudness


def _loudnorm_second_pass(loudness, profile: PremiumRenderProfile) -> str:
    """Return a deterministic single-pass loudnorm filter for the final mix.

    FFmpeg's two-pass measured-parameter mode is unreliable for short/high-LRA
    SFX-heavy mixes on the installed FFmpeg build: it can land materially above
    the requested integrated target. Keep the measured pass for provenance, but
    let the final encoder perform its own dynamic normalization and true-peak
    limiting.
    """
    return (
        f"loudnorm=I={profile.target_lufs:.1f}:LRA=7:TP={profile.max_true_peak_db:.1f}:"
        "linear=false:dual_mono=true"
    )


def finalize_video(
    input_video: str | Path,
    output_path: str | Path,
    profile: PremiumRenderProfile,
    *,
    audio_stems: Sequence[AudioStem] = (),
    subtitles: Sequence[SubtitleCue] = (),
    subtitle_style: SubtitleStyle | None = None,
    production_metadata: dict | None = None,
) -> QCReport:
    source = Path(input_video).resolve()
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise PremiumPipelineError(f"input video missing: {source}")

    work_dir = output.parent / ".premium_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    ass_path: Path | None = None
    video_filter = "null"
    if subtitles and profile.burn_in_subtitles:
        ass_path = work_dir / (output.stem + ".ass")
        write_ass(list(subtitles), ass_path, style=subtitle_style)
        video_filter = f"subtitles=filename='{_ass_filter_path(ass_path)}'"

    # Master the audio in a separate, deterministic two-pass chain.
    if audio_stems:
        mastered_input, loudness = _render_stem_mix(audio_stems, profile, work_dir)
    else:
        probe_audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(source)],
            capture_output=True, text=True,
        )
        if not probe_audio.stdout.strip():
            raise PremiumPipelineError("no source audio and no audio stems supplied")
        mastered_input, loudness = _render_source_audio_mix(source, profile, work_dir)

    loudnorm = _loudnorm_second_pass(loudness, profile)
    args = [
        "ffmpeg", "-y",
        "-i", str(source),
        "-i", str(mastered_input),
        "-filter_complex",
        f"[0:v]{video_filter}[vout];[1:a]{loudnorm},aresample={profile.sample_rate}[aout]",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", profile.video_codec,
        "-crf", str(profile.video_crf),
        "-preset", profile.video_preset,
        "-pix_fmt", profile.pix_fmt,
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-c:a", profile.audio_codec,
        "-b:a", profile.audio_bitrate,
        "-ar", str(profile.sample_rate),
        "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(output),
    ]
    _run(args)

    if not output.exists() or output.stat().st_size <= 0:
        raise PremiumPipelineError("finalizer returned without a valid output")

    report = validate_render(
        output,
        profile,
        subtitle_cues=list(subtitles) if subtitles else None,
    )
    write_provenance(
        output,
        profile=profile,
        audio_stems=audio_stems,
        subtitles=subtitles,
        extra={
            "input_sha256": _sha256(source),
            "premix_sha256": _sha256(Path(mastered_input)),
            "ass_path": str(ass_path) if ass_path else None,
            "loudness_measurement": {
                "integrated_lufs": loudness.integrated_lufs,
                "true_peak_db": loudness.true_peak_db,
                "lra": loudness.lra,
                "input_thresh": loudness.input_thresh,
                "target_offset": loudness.target_offset,
            },
            "production_graph": production_metadata or {},
        },
    )
    if not report.passed:
        raise QCError("; ".join(report.errors))
    return report


def validate_publish_assets(
    assets: Sequence[MediaAsset],
    *,
    platform: str,
    for_ad: bool,
) -> None:
    errors = validate_manifest_for_publish(
        assets,
        platform=platform,
        for_ad=for_ad,
    )
    if errors:
        raise PremiumPipelineError("\n".join(errors))


def write_provenance(
    output: Path,
    *,
    profile: PremiumRenderProfile,
    audio_stems: Sequence[AudioStem],
    subtitles: Sequence[SubtitleCue],
    extra: dict,
) -> Path:
    output_sha = _sha256(output)
    graph = extra.get("production_graph") if isinstance(extra, dict) else {}
    manifest = {
        "schema_version": "SCOS_PREMIUM_MEDIA_R1",
        "output": str(output),
        "output_sha256": output_sha,
        "render_profile": profile.__dict__,
        "audio_stems": [s.__dict__ for s in audio_stems],
        "subtitle_count": len(subtitles),
        "extra": extra,
        "learning_handoff": {
            "schema_version": "SCOS_LEARNING_HANDOFF_R1",
            "loop_run_id": graph.get("loop_run_id") if isinstance(graph, dict) else None,
            "graph_fingerprint": graph.get("graph_fingerprint") if isinstance(graph, dict) else None,
            "artifact_sha256": output_sha,
            "observed_telemetry_state": "NOT_OBSERVED",
            "note": "No retention/CTR/conversion observation is inferred or fabricated by rendering.",
        },
        "human_publish_gate": "NOT_APPROVED",
        "external_publish": "NOT_PERFORMED",
    }
    path = output.with_suffix(".provenance.json")
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
