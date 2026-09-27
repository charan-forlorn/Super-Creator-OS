from scos.media_analysis.contracts import MediaSourceProbe,MediaEvidence,CadenceStats,AdBoundary
from scos.media_analysis.pipeline import build_plan

def test_ad_boundary_removes_tail_and_ad_gap():
    p=MediaSourceProbe("x",60,1920,1080,30,1800,"h264","yuv420p","bt709","aac",48000,2,True)
    e=MediaEvidence(p,cadence=CadenceStats(30,1800,900,0.5,True),
                    ad_boundary=AdBoundary(50.0,56.0,0.9,"ad"))
    plan=build_plan(e)
    assert plan.ad_boundary_s==50.0
    assert all(end<=50.0 for _,end in plan.keep_ranges)

def test_adaptive_plan_flags_candidate():
    p=MediaSourceProbe("x",10,1920,1080,30,300,"h264","yuv420p","bt709","aac",48000,2,True)
    e=MediaEvidence(p,cadence=CadenceStats(30,300,140,0.5333,True))
    plan=build_plan(e,smoothness="adaptive")
    assert plan.interpolation_policy=="adaptive_smooth_plus_v2_candidate"
    assert plan.encoder_profile=="nvenc_p3_hq"
