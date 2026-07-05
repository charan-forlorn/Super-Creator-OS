import tempfile
import os
from scos.control_center import workflow_route_store as store
from scos.control_center import workflow_router as router


def test_append_and_load_and_find_and_latest():
    src = {"packet_id": "p-store-1", "source_agent": "chatgpt", "packet_type": "planning_prompt"}
    plan = router.plan_next_agent_route(
        session_id="sess-store",
        task_id="t-store",
        source_packet=src,
        result_packet={"result_status": "success"},
        created_at="2026-07-06T00:00:00Z",
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "routes.jsonl")
        store.append_route_plan(path, plan)
        loaded = store.load_route_plans(path)
        assert len(loaded) == 1
        found = store.find_route_plan(path, loaded[0].route_plan_id)
        assert found is not None
        latest = store.load_latest_route_plan_for_session(path, "sess-store")
        assert latest is not None and latest.route_plan_id == loaded[0].route_plan_id


def test_rejects_url_paths():
    try:
        store._validate_path("http://example.com/routes.jsonl")
        assert False, "should have raised"
    except ValueError:
        pass
