import httpx
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


@pytest.fixture
def ai_client(tmp_path):
    settings = Settings(state_dir=tmp_path / "state", ai_key="test-key", ai_model="test-model")
    return TestClient(create_app(settings), base_url="http://127.0.0.1")


@pytest.fixture
def fake_ai(monkeypatch):
    """Fake provider: `.reply` is message content or an exception; `.sent` holds requests."""

    class Fake:
        reply: object = ""
        sent: list[dict] = []

        def post(self, url, json, **_):
            self.sent.append(json)
            if isinstance(self.reply, Exception):
                raise self.reply
            body = {"choices": [{"message": {"content": self.reply}}]}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    fake = Fake()
    fake.sent = []
    monkeypatch.setattr("app.explain.httpx.post", fake.post)
    return fake
