from scos.control_center.capcut_adapter import create_draft,lint,repair_fast_caption

def test_capcut_adapter_contracts_are_callable():
    assert callable(create_draft)
    assert callable(lint)
    assert callable(repair_fast_caption)
