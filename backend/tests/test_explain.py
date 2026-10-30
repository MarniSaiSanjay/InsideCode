import httpx
import pytest

from app.config import Settings
from app.explain import AIUnavailable, chat, parse_json, suggest_terms
from tests.helpers import upload

AI = Settings(state_dir=None, ai_key="k", ai_model="m")
REPO = {
    "app/sessions.py": "def open_session(cookie):\n    return decode(cookie)\n",
    "app/views.py": "def index():\n    return 'hello'\n",
}


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
