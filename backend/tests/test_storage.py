import os
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.config import Limits, Settings
from app.indexing import ImportRejected
from app.main import create_app
from app.storage import Store, words
from tests.helpers import make_zip

AUTH = '''from flask import session


@bp.route("/logout")
def logout():
    """Clear the current session."""
    session.clear()
'''


def upload(client, files: dict[str, str], name: str = "repo.zip"):
    return client.post("/api/snapshots", files={"file": (name, make_zip(files))})


def test_words_split_identifiers():
    assert words("SecureCookieSessionInterface.open_session HTTPError v2 నమస్తే") == [
        "secure", "cookie", "session", "interface", "open", "session",
        "http", "error", "v", "2", "నమస్తే",
    ]  # fmt: skip


def test_upload_publishes_searchable_snapshot_with_exact_source(settings, client):
    summary = upload(client, {"repo/auth.py": AUTH, "repo/tests/test_auth.py": "x = 1\n"}).json()
    assert summary["files"] == 2 and summary["name"] == "repo.zip"
    assert client.get("/api/status").json()["snapshot"] == summary

    sid = summary["snapshot_id"]
    with closing(Store(settings.state_dir).connect(sid)) as db:
        rows = db.execute(
            "SELECT c.symbol, c.start_line, c.end_line, f.path, f.is_test FROM chunks_fts"
            " JOIN chunks c ON c.id = chunks_fts.rowid JOIN files f ON f.id = c.file_id"
            " WHERE chunks_fts MATCH 'clearing'"
        ).fetchall()
    assert [tuple(r) for r in rows] == [("logout", 4, 7, "auth.py", 0)]

    source = client.get(f"/api/snapshots/{sid}/files/1").json()
    assert source == {"id": 1, "path": "auth.py", "text": AUTH, "is_test": False}
    assert client.get(f"/api/snapshots/{sid}/files/99").status_code == 404


def test_failed_replacement_keeps_current_snapshot(client):
    first = upload(client, {"a.py": "x = 1\n"}).json()
    response = upload(client, {"README.md": "no python"})
    assert response.status_code == 400
    assert "No eligible" in response.json()["detail"]
    assert client.get("/api/status").json()["snapshot"] == first
    assert client.get(f"/api/snapshots/{first['snapshot_id']}/files/1").status_code == 200


def test_old_snapshot_ids_are_rejected_after_replacement(client):
    old = upload(client, {"a.py": "x = 1\n"}).json()["snapshot_id"]
    new = upload(client, {"b.py": "y = 2\n"}).json()["snapshot_id"]
    response = client.get(f"/api/snapshots/{old}/files/1")
    assert response.status_code == 409
    assert client.get(f"/api/snapshots/{new}/files/1").json()["path"] == "b.py"


def test_snapshot_survives_restart_and_cleans_interrupted_imports(settings, client):
    summary = upload(client, {"a.py": "x = 1\n"}).json()
    leftover = settings.state_dir / "snapshots" / "deadbeef.tmp"
    leftover.write_text("partial")

    restarted = TestClient(create_app(settings), base_url="http://127.0.0.1")
    assert restarted.get("/api/status").json()["snapshot"] == summary
    assert restarted.get(f"/api/snapshots/{summary['snapshot_id']}/files/1").status_code == 200
    assert not leftover.exists()
    assert len(list((settings.state_dir / "snapshots").iterdir())) == 1


def test_rejects_concurrent_import(settings):
    store = Store(settings.state_dir)
    with store.lock, pytest.raises(ImportRejected, match="in progress"):
        store.import_zip("x.zip", make_zip({"a.py": "x"}), settings.limits)


def test_rejects_oversized_upload_before_parsing(tmp_path):
    settings = Settings(state_dir=tmp_path, limits=Limits(max_zip_bytes=1))
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    response = client.post("/api/snapshots", files={"file": ("big.zip", b"x" * 2_000_000)})
    assert response.status_code == 413


def test_snapshot_db_is_read_only(settings, client):
    sid = upload(client, {"a.py": "x = 1\n"}).json()["snapshot_id"]
    with closing(Store(settings.state_dir).connect(sid)) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM files")


def test_failed_publish_leaves_no_partial_state(settings, monkeypatch):
    store = Store(settings.state_dir)
    first = store.import_zip("a.zip", make_zip({"a.py": "x = 1\n"}), settings.limits)

    def broken_replace(src, dst):
        if str(dst).endswith("current.json"):
            raise OSError("disk full")
        os.rename(src, dst)

    monkeypatch.setattr("app.storage.os.replace", broken_replace)
    with pytest.raises(OSError):
        store.import_zip("b.zip", make_zip({"b.py": "y = 2\n"}), settings.limits)
    assert store.current == first
    assert [p.name for p in store.dir.iterdir()] == [f"{first['snapshot_id']}.sqlite"]
