from scos.media_analysis.contracts import MediaSourceProbe,MediaEvidence,CadenceStats

def test_media_probe_to_dict():
    p=MediaSourceProbe("x.mp4",10,1920,1080,30,300,"h264","yuv420p","bt709","aac",48000,2,True)
    e=MediaEvidence(p,cadence=CadenceStats(30,300,150,0.5,True))
    assert e.to_dict()["source"]["fps"]==30
    assert e.to_dict()["cadence"]["duplicate_ratio"]==0.5
