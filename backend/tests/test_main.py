def test_health_reports_fts5_and_ai_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["fts5"] is True
    assert body["ai_configured"] is False
    assert body["limits"]["max_zip_bytes"] == 20 * 1024 * 1024


def test_rejects_foreign_origin(client):
    response = client.get("/api/health", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_rejects_foreign_host(client):
    response = client.get("/api/health", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_allows_local_dev_origin(client):
    response = client.get("/api/health", headers={"origin": "http://localhost:5173"})
    assert response.status_code == 200
