from pathlib import Path

from scos.agents.qa_agent import QAAgent


def test_missing_assets_fail_closed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scos.agents.qa_agent._REPO_ROOT", tmp_path)
    report = QAAgent().run({"edit_timeline": {
        "clips": [{"asset_path": "missing.png", "start": 0, "end": 1}],
        "total_duration": 1,
    }})
    assert report["status"] == "FAIL"
    assert report["passed"] is False
    assert report["missing_assets"] == ["missing.png"]


def test_real_asset_passes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("scos.agents.qa_agent._REPO_ROOT", tmp_path)
    asset = tmp_path / "real.png"
    asset.write_bytes(b"data")
    report = QAAgent().run({"edit_timeline": {
        "clips": [{"asset_path": "real.png", "start": 0, "end": 1}],
        "total_duration": 1,
    }})
    assert report["status"] == "PASS"
    assert report["passed"] is True
    assert report["missing_assets"] == []
