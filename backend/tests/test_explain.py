import httpx
import pytest

from app.config import Settings
from app.explain import (
    INSUFFICIENT,
    TESTS_ONLY,
    AIUnavailable,
    chat,
    evidence_context,
    parse_json,
    suggest_terms,
)
from tests.helpers import upload

AI = Settings(state_dir=None, ai_key="k", ai_model="m")
REPO = {
    "app/sessions.py": "def open_session(cookie):\n    return decode(cookie)\n",
    "app/views.py": "def index():\n    return 'hello'\n",
}
POINT = '{"sufficient": true, "points": [{"text": "Opens it.", "evidence": %s}]}'


def evidence(client, symbols=("open_session", "index"), files=REPO) -> dict:
    """An /api/explain body whose evidence is the chunks of `symbols`, in that order."""
    sid = upload(client, files).json()["snapshot_id"]
    q = " ".join(symbols)
    results = client.get("/api/search", params={"snapshot_id": sid, "q": q}).json()["results"]
    ids = {r["symbol"]: r["id"] for r in results}
    return {"snapshot_id": sid, "question": q, "chunk_ids": [ids[s] for s in symbols]}


def test_chat_requires_configuration():
    with pytest.raises(AIUnavailable, match="not configured"):
        chat(Settings(state_dir=None), "s", "u", 1, 10)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
def test_chat_failures_become_unavailable(fake_ai, failure):
    fake_ai.reply = failure
    with pytest.raises(AIUnavailable):
        chat(AI, "s", "u", 1, 10)


@pytest.mark.parametrize("content", [None, {"a": 1}, ["x"], 3])
def test_chat_rejects_non_text_content(fake_ai, content):
    fake_ai.reply = content
    with pytest.raises(AIUnavailable):
        chat(AI, "s", "u", 1, 10)


def test_parse_json_tolerates_fences_and_rejects_garbage():
    assert parse_json('Sure:\n```json\n["a", "b"]\n```') == ["a", "b"]
    assert parse_json('{"x": [1]} trailing') == {"x": [1]}
    for bad in ["no json here", "[unclosed", "} {"]:
        with pytest.raises(AIUnavailable):
            parse_json(bad)


def test_suggest_terms_keeps_only_valid_identifiers(fake_ai):
    fake_ai.reply = '["open_session", "open_session", "rm -rf /", 42, "Cookie.load", "a b"]'
    assert suggest_terms(AI, "where are cookies read?") == ["open_session", "Cookie.load"]
    assert fake_ai.sent[0]["model"] == "m"
    fake_ai.reply = '{"terms": ["x"]}'
    with pytest.raises(AIUnavailable):
        suggest_terms(AI, "q")


def test_expansion_adds_results_and_keeps_original_ones(ai_client, fake_ai):
    sid = upload(ai_client, REPO).json()["snapshot_id"]
    params = {"snapshot_id": sid, "q": "how is the hello page shown"}
    plain = ai_client.get("/api/search", params=params).json()
    assert fake_ai.sent == []  # no AI call without consent

    fake_ai.reply = '["open_session"]'
    expanded = ai_client.get("/api/search", params=params | {"expand": True}).json()
    assert expanded["suggested_terms"] == ["open_session"] and expanded["ai_note"] is None
    reasons = {r["symbol"]: r["reasons"] for r in expanded["results"]}
    assert reasons["open_session"] == ["AI-suggested term"]
    assert {r["symbol"] for r in plain["results"]} <= set(reasons)


def test_expansion_failure_falls_back_to_local_search(ai_client, fake_ai):
    sid = upload(ai_client, REPO).json()["snapshot_id"]
    params = {"snapshot_id": sid, "q": "open_session"}
    fake_ai.reply = httpx.ReadTimeout("slow")
    body = ai_client.get("/api/search", params=params | {"expand": True}).json()
    assert body["suggested_terms"] == [] and "local search" in body["ai_note"]
    assert body["results"] == ai_client.get("/api/search", params=params).json()["results"]


def test_explanation_sends_previewed_context_and_cites_index_locations(ai_client, fake_ai):
    body = evidence(ai_client)
    context = ai_client.post("/api/explain/context", json=body).json()["context"]
    assert "[E1] sessions.py lines 1-2" in context and "[E2] views.py" in context
    assert fake_ai.sent == []  # preview never calls the provider

    fake_ai.reply = POINT % '["E1", "E1"]'
    answer = ai_client.post("/api/explain", json=body).json()
    assert fake_ai.sent[0]["messages"][1]["content"] == context
    assert answer["sufficient"] and answer["note"] is None
    [cite] = answer["points"][0]["evidence"]
    assert cite | {"chunk_id": 0, "file_id": 0} == {
        "id": "E1",
        "chunk_id": 0,
        "file_id": 0,
        "path": "sessions.py",
        "start_line": 1,
        "end_line": 2,
        "is_test": False,
    }


@pytest.mark.parametrize(
    "reply",
    [
        POINT % '["E9"]',
        POINT % "[]",
        POINT % '[["E1"]]',
        '{"sufficient": true, "points": [{"text": "No citation."}]}',
        '{"sufficient": "yes", "points": []}',
        '["E1"]',
        "not json",
    ],
)
def test_explanation_rejects_unknown_missing_or_malformed_citations(ai_client, fake_ai, reply):
    body = evidence(ai_client)
    fake_ai.reply = reply
    response = ai_client.post("/api/explain", json=body)
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]


def test_explanation_reports_insufficient_or_test_only_evidence(ai_client, fake_ai):
    files = REPO | {"tests/test_sessions.py": "def test_open_session():\n    open_session(1)\n"}
    body = evidence(ai_client, ("test_open_session",), files)
    fake_ai.reply = '{"sufficient": false, "points": []}'
    assert ai_client.post("/api/explain", json=body).json()["note"] == INSUFFICIENT
    fake_ai.reply = POINT % '["E1"]'
    answer = ai_client.post("/api/explain", json=body).json()
    assert answer["note"] == TESTS_ONLY and not answer["sufficient"]


def test_context_lists_question_names_no_snippet_contains():
    row = {"path": "app.py", "symbol": "FlaskClient.open", "start_line": 1, "end_line": 2}
    context = evidence_context("Is GraphQL in FlaskClient? Please say", [row | {"text": "x"}])
    assert context.startswith("Question: Is GraphQL in FlaskClient? Please say\n")
    assert "\nNot in any snippet: GraphQL, Please\n" in context


def test_explanation_validates_requested_evidence(ai_client):
    body = evidence(ai_client)
    missing = ai_client.post("/api/explain", json=body | {"chunk_ids": [999]})
    assert missing.status_code == 404
    too_many = ai_client.post("/api/explain/context", json=body | {"chunk_ids": [1] * 6})
    assert too_many.status_code == 422
    stale = ai_client.post("/api/explain/context", json=body | {"snapshot_id": "old"})
    assert stale.status_code == 409


def test_general_answer_sends_only_the_question(ai_client, fake_ai):
    fake_ai.reply = "Password hashing stores a one-way digest."
    body = {"question": "What is password hashing?"}
    assert ai_client.post("/api/general", json=body).json() == {"answer": fake_ai.reply}
    assert fake_ai.sent[0]["messages"][1]["content"] == body["question"]
    fake_ai.reply = "  "
    assert ai_client.post("/api/general", json=body).status_code == 503


@pytest.mark.parametrize("path", ["p/" * 400, "ఆ/" * 400])
def test_context_stays_under_20_kib_with_largest_inputs(path):
    row = {"path": path, "symbol": None, "start_line": 1, "end_line": 99999, "text": "é" * 9000}
    context = evidence_context("ఆ" * 500, [row] * 5)
    assert len(context.encode()) < 20 * 1024 and context.count("(truncated)") == 5
    assert len(evidence_context("q", [row | {"text": "x = 1"}])) < 1000  # short code is kept whole
