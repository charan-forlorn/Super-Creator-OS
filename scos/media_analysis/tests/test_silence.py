from scos.media_analysis.silence import complement_ranges
from scos.media_analysis.contracts import SilenceSpan

def test_complement_ranges():
    r=complement_ranges(10,[SilenceSpan(0,2,2),SilenceSpan(5,7,2)])
    assert r==[(2,5),(7,10)]
