def test_module_imports():
    from scos.media_analysis.temporal_quality import verify_temporal_quality
    assert callable(verify_temporal_quality)
