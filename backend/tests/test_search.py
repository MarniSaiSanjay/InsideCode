from contextlib import closing

from app.search import LIMIT, PER_FILE, search, terms
from app.storage import Store
from tests.helpers import upload

REPO = {
    "app/sessions.py": '''class SessionStore:
    def load_session(self, cookie):
        """Load the signed session cookie."""
        return decode(cookie)


def save_session(response):
    response.set_cookie("session")
''',
    "tests/test_sessions.py": """def test_load_session_reads_signed_cookie():
    assert load_session("signed cookie")
""",
}


def test_terms_drop_filler_and_split_identifiers():
    assert terms("Where is the loadSession / save_session code? save it") == [
        "load", "session", "save",
    ]  # fmt: skip
    assert terms("") == terms("?? the !!") == []


def test_search_ranks_regions_with_reasons(client):
    sid = upload(client, REPO).json()["snapshot_id"]
    body = client.get("/api/search", params={"snapshot_id": sid, "q": "load_session"}).json()
    first = body["results"][0]
    assert (first["path"], first["symbol"], first["start_line"], first["end_line"]) == (
        "app/sessions.py", "SessionStore.load_session", 2, 4,
    )  # fmt: skip
    assert "exact symbol" in first["reasons"] and "keyword match" in first["reasons"]
    assert first["text"].startswith("    def load_session")

    results = client.get(
        "/api/search", params={"snapshot_id": sid, "q": "how is the signed session cookie loaded"}
    ).json()["results"]
    assert [r["is_test"] for r in results][-1] is True
    assert results[0]["symbol"] == "SessionStore.load_session"


def test_search_handles_syntax_and_no_match(client):
    sid = upload(client, REPO).json()["snapshot_id"]
    for q in ['"unbalanced', "NEAR( OR AND *", "zzzqqq", "", "a'; DROP TABLE files;--"]:
        response = client.get("/api/search", params={"snapshot_id": sid, "q": q})
        assert response.status_code == 200
        assert response.json()["results"] == []
    too_long = client.get("/api/search", params={"snapshot_id": sid, "q": "x" * 501})
    assert too_long.status_code == 422
    stale = client.get("/api/search", params={"snapshot_id": "old", "q": "session"})
    assert stale.status_code == 409


def test_search_limits_results_per_file_and_total(settings, client):
    repo = {
        f"pkg/m{i}.py": "".join(f"def cookie_{j}():\n    pass\n\n\n" for j in range(5))
        for i in range(5)
    }
    sid = upload(client, repo).json()["snapshot_id"]
    with closing(Store(settings.state_dir).connect(sid)) as db:
        results = search(db, "cookie")
    paths = [r["path"] for r in results]
    assert len(results) == LIMIT
    assert max(paths.count(p) for p in paths) == PER_FILE


def test_exact_symbols_made_of_stopwords_are_found(settings, client):
    repo = {
        "m.py": "def get_all():\n    pass\n\n\nclass Box:\n    def __get__(self):\n        pass\n"
    }
    sid = upload(client, repo).json()["snapshot_id"]
    with closing(Store(settings.state_dir).connect(sid)) as db:
        for q, symbol in [
            ("get_all", "get_all"),
            ("Where is get_all?", "get_all"),
            ("__get__", "Box.__get__"),
        ]:
            assert search(db, q)[0]["symbol"] == symbol, q


def test_qualified_name_ranks_its_own_method_first(client):
    repo = {
        "a/blueprints.py": "class Setup:\n    def add_rule(self, rule):\n        add_rule(rule)\n",
        "b/app.py": "class App:\n    def add_rule(self, rule):\n        return rule\n",
    }
    sid = upload(client, repo).json()["snapshot_id"]
    body = client.get("/api/search", params={"snapshot_id": sid, "q": "App.add_rule"}).json()
    assert body["results"][0]["symbol"] == "App.add_rule"
    assert "exact qualified name" in body["results"][0]["reasons"]
