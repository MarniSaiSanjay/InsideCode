import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(state_dir=tmp_path / "state")


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings), base_url="http://127.0.0.1")
