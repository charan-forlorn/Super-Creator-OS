from scos.control_center import workflow_router_models as m


def test_frozenmap_immutable_and_to_dict_order():
    fm = m.FrozenMap({"b": 2, "a": 1})
    d = fm.to_dict()
    assert isinstance(d, dict)
    assert d["a"] == 1 and d["b"] == 2


def test_agent_route_rule_to_dict_key_order():
    rule = m.AgentRouteRule.of(
        rule_id="r1",
        name="n",
        source_agent="chatgpt",
        source_packet_type="planning_prompt",
        result_status="success",
        review_decision=None,
        target_agent="claude_code",
        target_packet_type="implementation_prompt",
        priority="normal",
        requires_operator_review=True,
        enabled=True,
        metadata={"z": 1},
    )
    keys = list(rule.to_dict().keys())
    expected = [
        "rule_id",
        "name",
        "source_agent",
        "source_packet_type",
        "result_status",
        "review_decision",
        "target_agent",
        "target_packet_type",
        "priority",
        "requires_operator_review",
        "enabled",
        "metadata",
    ]
    assert keys == expected
