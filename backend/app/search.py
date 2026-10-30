import re
import sqlite3
from collections import defaultdict

from .storage import symbol_name, words

MAX_QUERY_CHARS = 500
MAX_TERMS = 16
CANDIDATES = 50
RRF_K = 60
PER_FILE = 3
LIMIT = 10
TEST_WEIGHT = 0.5  # newcomers usually need the implementation; tests stay visible but labelled
IDENTIFIER = re.compile(r"[A-Za-z_][\w.]*\w|[A-Za-z]")
CODE_LIKE = re.compile(r"[_.]|[a-z][A-Z]")
# Question filler that carries no signal about where code lives.
STOPWORDS = set(
    """a about all am an and any are as at be been being but by can could did do does doing
    for from get gets got had has have here how i if in into is it its me my of on or our
    should so some than that the their them then there these they this those to us was we
    were what when where which who why will with would you your look looking start starting
    read reading change modify code defined implemented located happen happens""".split()
)

RESULT_SQL = """
SELECT c.id, c.file_id, f.path, c.kind, c.symbol, c.start_line, c.end_line, c.text, f.is_test
FROM chunks c JOIN files f ON f.id = c.file_id WHERE c.id = ?
"""


def terms(query: str) -> list[str]:
    """Distinct useful words from the question, in order."""
    found = dict.fromkeys(w for w in words(query[:MAX_QUERY_CHARS]) if len(w) > 1)
    return [w for w in found if w not in STOPWORDS][:MAX_TERMS]


def _fts(db: sqlite3.Connection, useful: list[str], columns: str = "") -> list[int]:
    """Chunks matching any term (terms are quoted, so FTS syntax in the query is inert)."""
    if not useful:
        return []
    match = columns + "(" + " OR ".join(f'"{t}"' for t in useful) + ")"
    rows = db.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?"
        " ORDER BY bm25(chunks_fts, 10.0, 5.0, 1.0) LIMIT ?",
        (match, CANDIDATES),
    )
    return [row[0] for row in rows]


def _exact_symbols(db: sqlite3.Connection, query: str) -> list[int]:
    """Chunks named by a code-like identifier in the query, or by a one-word query."""
    tokens = IDENTIFIER.findall(query[:MAX_QUERY_CHARS])
    names = {symbol_name(t) for t in tokens if len(tokens) == 1 or CODE_LIKE.search(t)}
    names = sorted(names)[:MAX_TERMS]
    if not names:
        return []
    marks = ",".join("?" * len(names))
    rows = db.execute(
        f"SELECT c.id FROM chunks c JOIN files f ON f.id = c.file_id WHERE c.name IN ({marks})"
        " ORDER BY f.is_test, c.id LIMIT ?",
        (*names, CANDIDATES),
    )
    return [row[0] for row in rows]


def search(db: sqlite3.Connection, query: str, hybrid: bool = True) -> list[dict]:
    """Rank code regions for a question; hybrid adds symbol/path matching to keyword search."""
    useful = terms(query)
    lists = {"keyword match": _fts(db, useful)}
    if hybrid:
        lists["exact symbol"] = _exact_symbols(db, query)
        lists["symbol/path match"] = _fts(db, useful, "{symbol path} : ")

    scores: dict[int, float] = defaultdict(float)
    reasons: dict[int, list[str]] = defaultdict(list)
    for reason, ids in lists.items():
        for rank, chunk_id in enumerate(ids):
            scores[chunk_id] += 1 / (RRF_K + rank + 1)
            reasons[chunk_id].append(reason)

    rows = {i: dict(db.execute(RESULT_SQL, (i,)).fetchone()) for i in scores}
    for chunk_id, row in rows.items():
        if row["is_test"]:
            scores[chunk_id] *= TEST_WEIGHT

    results, per_file = [], defaultdict(int)
    for chunk_id in sorted(scores, key=scores.get, reverse=True):
        row = rows[chunk_id]
        if per_file[row["path"]] == PER_FILE:
            continue
        per_file[row["path"]] += 1
        results.append(row | {"is_test": bool(row["is_test"]), "reasons": reasons[chunk_id]})
        if len(results) == LIMIT:
            break
    return results
