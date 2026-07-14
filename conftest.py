import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "local_acceptance: bounded local acceptance against the certified artifact (no transport)"
    )


@pytest.fixture
def tmp(tmp_path):
    return tmp_path

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "store.json")