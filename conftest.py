import pytest

@pytest.fixture
def tmp(tmp_path):
    return tmp_path

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path