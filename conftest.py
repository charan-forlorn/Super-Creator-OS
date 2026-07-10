import pytest

@pytest.fixture
def tmp(tmp_path):
    return tmp_path

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "store.json")