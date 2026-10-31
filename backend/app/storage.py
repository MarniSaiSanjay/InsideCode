import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from . import architecture
from .config import Limits
from .indexing import Deadline, ImportRejected, SourceFile, parse_file, read_zip
from .languages import is_test_path, language_for

SCHEMA_VERSION = 4  # bump when SCHEMA or the summary changes; older snapshots are then discarded
SCHEMA = """
CREATE TABLE files (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, text TEXT NOT NULL,
    sha256 TEXT NOT NULL, is_test INTEGER NOT NULL
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id), kind TEXT NOT NULL,
    symbol TEXT, name TEXT, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX chunks_name ON chunks(name);
CREATE TABLE architecture (data TEXT NOT NULL);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    symbol, path, code, content='', tokenize='porter unicode61'
);
"""
# CamelCase parts, lowercase runs, digits, and non-ASCII words (kept with their combining marks).
WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+|[^\W\d_A-Za-z][^\x00-\x7f\s]*")


class StaleSnapshot(Exception):
    """The requested snapshot is no longer the published one."""


def fts5_available() -> bool:
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
            db.execute("INSERT INTO probe VALUES ('hello world')")
            return bool(db.execute("SELECT 1 FROM probe WHERE probe MATCH 'hello'").fetchall())
    except sqlite3.Error:
        return False


def words(text: str) -> list[str]:
    """Lowercase words with snake_case and CamelCase identifiers split apart."""
    return [w.lower() for w in WORD.findall(text)]


def symbol_name(symbol: str | None) -> str | None:
    """Lowercase final part of a dotted symbol, used for exact-name lookups."""
    return symbol.rsplit(".", 1)[-1].lower() if symbol else None


def _build(path: Path, files: list[SourceFile], deadline: Deadline) -> tuple[int, int]:
    """Index files; return (chunks, definitions), counting each named function or class once."""
    count = 0
    overview: list[architecture.FileInfo] = []
    with closing(sqlite3.connect(path)) as db:
        db.executescript(SCHEMA)
        for file in files:
            deadline.check()
            digest = hashlib.sha256(file.text.encode()).hexdigest()
            file_id = db.execute(
                "INSERT INTO files (path, text, sha256, is_test) VALUES (?, ?, ?, ?)",
                (file.path, file.text, digest, is_test_path(file.path)),
            ).lastrowid
            path_words = " ".join(words(file.path))
            chunks, facts = parse_file(file)
            if not is_test_path(file.path):
                spans: dict[str, tuple[str, int, int]] = {}
                for c in chunks:  # long definitions are split into several chunks
                    if c.kind in ("function", "class") and c.symbol:
                        kind, first, last = spans.get(c.symbol, (c.kind, c.start, c.end))
                        spans[c.symbol] = (kind, min(first, c.start), max(last, c.end))
                defs = [(symbol, *span) for symbol, span in spans.items()]
                overview.append(architecture.FileInfo(file.path, file.text, defs, facts))
            for chunk in chunks:
                chunk_id = db.execute(
                    "INSERT INTO chunks (file_id, kind, symbol, name, start_line, end_line, text)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_id,
                        chunk.kind,
                        chunk.symbol,
                        symbol_name(chunk.symbol),
                        chunk.start,
                        chunk.end,
                        chunk.text,
                    ),
                ).lastrowid
                db.execute(
                    "INSERT INTO chunks_fts (rowid, symbol, path, code) VALUES (?, ?, ?, ?)",
                    (
                        chunk_id,
                        " ".join(words(chunk.symbol or "")),
                        path_words,
                        " ".join(words(chunk.text)),
                    ),
                )
                count += 1
        # Long definitions are split into several chunks that share a symbol.
        (definitions,) = db.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT file_id, symbol FROM chunks"
            " WHERE kind IN ('function', 'class') AND symbol IS NOT NULL)"
        ).fetchone()
        deadline.check()
        data = json.dumps(architecture.build(overview, deadline.check))
        db.execute("INSERT INTO architecture (data) VALUES (?)", (data,))
        db.commit()
    return count, definitions


class Store:
    """Published snapshots: one SQLite file each, with current.json naming the live one."""

    def __init__(self, state_dir: Path):
        state_dir = state_dir.resolve()
        self.dir = state_dir / "snapshots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.pointer = state_dir / "current.json"
        self.lock = threading.Lock()
        self.current = self._load_current()
        self._remove_unpublished()

    def _db_path(self, snapshot_id: str) -> Path:
        return self.dir / f"{snapshot_id}.sqlite"

    def _load_current(self) -> dict | None:
        try:
            current = json.loads(self.pointer.read_text())
            usable = current["schema"] == SCHEMA_VERSION
            return current if usable and self._db_path(current["snapshot_id"]).is_file() else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _remove_unpublished(self) -> None:
        keep = self._db_path(self.current["snapshot_id"]) if self.current else None
        for path in self.dir.iterdir():
            if path != keep:
                path.unlink(missing_ok=True)

    def import_zip(self, name: str, data: bytes, limits: Limits) -> dict:
        if not self.lock.acquire(blocking=False):
            raise ImportRejected("Another import is in progress")
        try:
            deadline = Deadline(limits.import_seconds)
            contents = read_zip(data, limits, deadline)
            snapshot_id = secrets.token_hex(8)
            final = self._db_path(snapshot_id)
            temp = final.with_suffix(".tmp")
            chunk_count, definitions = _build(temp, contents.files, deadline)
            deadline.check()
            os.replace(temp, final)
            summary = {
                "snapshot_id": snapshot_id,
                "schema": SCHEMA_VERSION,
                "name": name,
                "files": len(contents.files),
                "chunks": chunk_count,
                "definitions": definitions,
                "languages": sorted({language_for(file.path).name for file in contents.files}),
                "skipped": dict(contents.skipped),
            }
            # Staged in snapshots/ so the cleanup below also removes it if publishing fails.
            pending = self.dir / "current.json"
            pending.write_text(json.dumps(summary))
            os.replace(pending, self.pointer)
            self.current = summary
            return summary
        finally:
            try:
                self._remove_unpublished()
            finally:
                self.lock.release()

    def connect(self, snapshot_id: str) -> sqlite3.Connection:
        current = self.current
        if not current or current["snapshot_id"] != snapshot_id:
            raise StaleSnapshot
        try:
            db = sqlite3.connect(f"{self._db_path(snapshot_id).as_uri()}?mode=ro", uri=True)
        except sqlite3.OperationalError as exc:
            raise StaleSnapshot from exc
        db.row_factory = sqlite3.Row
        return db

    def architecture(self, snapshot_id: str) -> dict:
        with closing(self.connect(snapshot_id)) as db:
            return json.loads(db.execute("SELECT data FROM architecture").fetchone()[0])

    def source(self, snapshot_id: str, file_id: int) -> dict | None:
        with closing(self.connect(snapshot_id)) as db:
            row = db.execute(
                "SELECT id, path, text, is_test FROM files WHERE id = ?", (file_id,)
            ).fetchone()
        return dict(row) | {"is_test": bool(row["is_test"])} if row else None
