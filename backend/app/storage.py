import sqlite3
from contextlib import closing


def fts5_available() -> bool:
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
            db.execute("INSERT INTO probe VALUES ('hello world')")
            return bool(db.execute("SELECT 1 FROM probe WHERE probe MATCH 'hello'").fetchall())
    except sqlite3.Error:
        return False
