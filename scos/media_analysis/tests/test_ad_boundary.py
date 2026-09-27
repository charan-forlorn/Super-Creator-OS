from scos.media_analysis.ad_boundary import infer_final_ad_boundary
from scos.media_analysis.contracts import SceneBoundary,SilenceSpan

def test_infer_ad_boundary():
    result=infer_final_ad_boundary(60,[SceneBoundary(56.0,0.3)],[SilenceSpan(50.0,52.2,2.2)])
    assert result is not None
    assert result.content_end==50.0
