import os
from scos.ai.typesafe_jev import JevDecision,should_promote_smooth_plus,advise_smooth_plus

def test_typesafe_is_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY",raising=False)
    result=advise_smooth_plus({"duplicate_ratio":0.5})
    assert result.status=="UNAVAILABLE"
    assert should_promote_smooth_plus(result,True) is False

def test_typesafe_promotion_requires_confidence():
    low=JevDecision("REVIEW","jev-1.13.0",{"render_lane":{"choice":"smooth_plus"}},0.7)
    high=JevDecision("PASS","jev-1.13.0",{"render_lane":{"choice":"smooth_plus"}},0.9)
    assert should_promote_smooth_plus(low,True) is False
    assert should_promote_smooth_plus(high,True) is True
