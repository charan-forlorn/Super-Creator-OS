import math
import struct
import wave

from scos.premium_media.audio_reactivity import analyze_audio
from scos.premium_media.benchmark import BenchmarkCase, benchmark_case
from scos.premium_media.compositing import CompositeSpec, MaskSpec
from scos.premium_media.lookdev import LookProfile
from scos.premium_media.scene3d import Camera3D, DepthLayer, ProductScene
from scos.premium_media.shot_intelligence import plan_storyboard, storyboard_to_motion_shell
from scos.premium_media.transitions import TransitionRuntimeSpec, compile_transition_filter
from scos.premium_media.typography import TypographyPlan, TypographyStyle, WordCue
from scos.premium_media.creative_graph import CreativeBrief, ProductionGraph

def _write_tone(path):
    rate = 8000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        for i in range(rate):
            amp = 28000 if i < rate // 2 else 3000
            sample = int(amp * math.sin(2 * math.pi * 220 * i / rate))
            wf.writeframes(struct.pack("<h", sample))

def test_r2_compositing_and_transitions_are_bounded():
    spec = CompositeSpec(opacity=.8, blur_px=4, glow=.5, mask=MaskSpec("ellipse", 12, False))
    assert spec.validate() == ()
    assert TransitionRuntimeSpec("whip", .4, "ease_in_out", "forward").validate("test") == ()
    assert compile_transition_filter(TransitionRuntimeSpec("whip", .4)) == "whip:forward:0.400"

def test_r2_rejects_invalid_compositing():
    assert CompositeSpec(opacity=1.2).validate()
    assert TransitionRuntimeSpec("cut", .2).validate("test")

def test_r3_uses_real_audio_bytes(tmp_path):
    audio = tmp_path / "tone.wav"; _write_tone(audio)
    result = analyze_audio(audio)
    assert result.duration_s > .9
    assert result.sample_rate == 8000
    assert len(result.rms) > 2
    assert result.events

def test_r4_typography_word_timing_is_validated():
    plan = TypographyPlan(TypographyStyle("kinetic", size_px=64),
        (WordCue("Build", 0, .4, 1), WordCue("faster", .4, .9, .5)))
    assert plan.validate() == ()
    bad = TypographyPlan(words=(WordCue("x", .5, .4),))
    assert bad.validate()

def test_r5_lookdev_fingerprint_and_filter(tmp_path):
    lut = tmp_path / "look.cube"; lut.write_text("TITLE test\n")
    a = LookProfile("cinematic", contrast=1.08, saturation=1.05, lut_path=str(lut))
    b = LookProfile("cinematic", contrast=1.08, saturation=1.05, lut_path=str(lut))
    assert a.validate() == ()
    assert a.fingerprint() == b.fingerprint()
    assert "lut3d" in a.ffmpeg_filter()

def test_r6_product_scene_validation():
    scene = ProductScene("phone", camera=Camera3D(z=1200, fov_deg=45),
        layers=(DepthLayer("back", 300, .5), DepthLayer("product", 0, 1.0)))
    assert scene.validate() == ()
    assert ProductScene("bad", camera=Camera3D(z=0)).validate()

def test_r7_storyboard_planner_covers_ad_arc():
    plan = plan_storyboard("sell the product", 30, "ad")
    assert plan.validate() == ()
    assert [s.purpose for s in plan.shots][:3] == ["hook", "problem", "demo"]
    assert plan.shots[-1].purpose == "cta"
    shell = storyboard_to_motion_shell(plan)
    assert shell.validate() == ()
    assert shell.shots[0].purpose == "hook"

def test_r8_benchmark_case_is_repeatable():
    case = BenchmarkCase("ad-001", "ad", 30, "launch a new product")
    a = benchmark_case(case); b = benchmark_case(case)
    assert a == b
    assert a.passed
    assert set(a.capabilities) == {"storyboard", "compositing", "typography", "lookdev", "scene3d"}

def test_graph_fingerprint_changes_when_premium_runtime_is_added():
    brief = CreativeBrief("p1", "objective", "ad")
    base = ProductionGraph(brief=brief)
    upgraded = ProductionGraph(brief=brief, compositing=CompositeSpec(opacity=.9))
    assert base.fingerprint() != upgraded.fingerprint()
    props = upgraded.to_remotion_props()
    assert props["production_graph"]["compositing"]["opacity"] == .9
