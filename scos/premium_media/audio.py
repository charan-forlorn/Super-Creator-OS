"""Premium audio mix/finish planning for commercial-ready video."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import AudioRole, AudioStem, PremiumRenderProfile


@dataclass(frozen=True)
class AudioMixPlan:
    input_args: tuple[str, ...]
    filter_complex: str
    output_label: str = "[aout]"


def role_gain_preset(role: AudioRole) -> float:
    return {
        AudioRole.VOICE: 0.0,
        AudioRole.MUSIC: -15.0,
        AudioRole.SFX: -9.0,
        AudioRole.AMBIENCE: -22.0,
    }[role]


def _source_chain(index: int, stem: AudioStem) -> str:
    delay_ms = max(0, round(stem.start_s * 1000))
    parts = [f"aresample=48000", f"adelay={delay_ms}:all=1"]
    if stem.trim_start_s > 0:
        parts.append(f"atrim=start={stem.trim_start_s:.3f}")
    if stem.trim_end_s is not None:
        parts.append(f"atrim=end={stem.trim_end_s:.3f}")
    if stem.role == AudioRole.VOICE:
        parts.extend([
            "highpass=f=70",
            "lowpass=f=17000",
            "afftdn=nr=10:nf=-35:tn=1",
            "deesser=i=0.35:m=0.5:f=0.5",
        ])
    elif stem.role == AudioRole.MUSIC:
        parts.extend([
            "highpass=f=35",
            "lowpass=f=19000",
        ])
    parts.append(f"volume={stem.gain_db:.2f}dB")
    if abs(stem.pan) > 0.001:
        balance = max(-1.0, min(1.0, stem.pan))
        parts.append(f"stereotools=mlev=1:rlev=1:balance_in={balance:.3f}")
    return f"[{index}:a]" + ",".join(parts) + f"[a{index}]"


def build_mix_plan(
    stems: Sequence[AudioStem],
    profile: PremiumRenderProfile,
    *,
    input_index_offset: int = 0,
    include_loudnorm: bool = True,
) -> AudioMixPlan:
    enabled = [s for s in stems if s.enabled]
    if not enabled:
        raise ValueError("audio mix requires at least one enabled stem")

    input_args: list[str] = []
    filters: list[str] = []
    voice: list[str] = []
    music: list[str] = []
    other: list[str] = []

    for index, stem in enumerate(enabled):
        input_args.extend(["-i", str(stem.asset_id)])
        source_index = index + input_index_offset
        filters.append(_source_chain(source_index, stem))
        label = f"[a{source_index}]"
        if stem.role == AudioRole.VOICE:
            voice.append(label)
        elif stem.role == AudioRole.MUSIC:
            music.append(label)
        else:
            other.append(label)

    buses: list[str] = []

    def materialize_bus(labels: list[str], name: str) -> str | None:
        if not labels:
            return None
        if len(labels) == 1:
            return labels[0]
        label = f"[{name}]"
        filters.append(
            "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[{name}]"
        )
        return label

    voice_bus = materialize_bus(voice, "voicebus")
    music_bus = materialize_bus(music, "musicbus")
    other_bus = materialize_bus(other, "otherbus")

    if music_bus and voice_bus:
        filters.append(f"{voice_bus}asplit=2[voice_sc][voice_mix]")
        filters.append(
            f"{music_bus}[voice_sc]sidechaincompress="
            "threshold=0.02:ratio=8:attack=20:release=220:makeup=1:mix=1[ducked]"
        )
        voice_bus = "[voice_mix]"
        music_bus = "[ducked]"

    buses.extend([bus for bus in (voice_bus, music_bus, other_bus) if bus])

    if not buses:
        raise ValueError("audio mix produced no buses")
    if len(buses) == 1:
        filters.append(f"{buses[0]}anull[premix]")
    else:
        filters.append(
            "".join(buses)
            + f"amix=inputs={len(buses)}:duration=longest:normalize=0[premix]"
        )
    filters.append(
        "[premix]highpass=f=55,lowpass=f=18500,"
        "acompressor=threshold=-18dB:ratio=2.2:attack=8:release=90:makeup=1.2"
        + (f",loudnorm=I={profile.target_lufs:.1f}:LRA=7:TP={profile.max_true_peak_db:.1f}:dual_mono=true" if include_loudnorm else "")
        + f",aresample={profile.sample_rate}[aout]"
    )
    return AudioMixPlan(
        tuple(input_args),
        ";".join(filters),
        output_label="[aout]",
    )


def build_finish_command(
    input_video: str,
    stems: Sequence[AudioStem],
    output_path: str,
    profile: PremiumRenderProfile,
) -> list[str]:
    plan = build_mix_plan(stems, profile, input_index_offset=1)
    args = [
        "ffmpeg", "-y", "-i", input_video, *plan.input_args,
        "-filter_complex", plan.filter_complex,
        "-map", "0:v:0", "-map", plan.output_label,
        "-c:v", profile.video_codec, "-crf", str(profile.video_crf),
        "-preset", profile.video_preset, "-pix_fmt", profile.pix_fmt,
        "-c:a", profile.audio_codec, "-b:a", profile.audio_bitrate,
        "-ar", str(profile.sample_rate), "-ac", "2",
        "-movflags", "+faststart",
        "-shortest", output_path,
    ]
    return args
