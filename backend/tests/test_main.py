from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_fts5_and_ai_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["fts5"] is True
    assert body["ai_configured"] is False
    assert body["limits"]["max_zip_bytes"] == 20 * 1024 * 1024
    assert {"Python", "Go"} <= set(body["languages"])


def test_rejects_foreign_origin(client):
    response = client.get("/api/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_rejects_foreign_host(client):
    response = client.get("/api/health", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_allows_local_dev_origin(client):
    response = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert response.status_code == 200


def test_serves_built_ui_beside_the_api(tmp_path):
    ui = tmp_path / "dist"
    ui.mkdir()
    (ui / "index.html").write_text("<h1>InsideCode</h1>")
    app = create_app(Settings(state_dir=tmp_path / "state", ui_dir=ui))
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/").text == "<h1>InsideCode</h1>"
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/", headers={"host": "evil.example"}).status_code == 403
