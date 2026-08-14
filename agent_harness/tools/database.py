"""query_database — structured lookups against a local SQLite demo database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_harness.scenarios.failure_engine import FailureEngine
from agent_harness.tools.base import BaseTool

_SEED_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    plan TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    item TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL
);
"""

_SEED_ROWS: dict[str, list[tuple]] = {
    "users": [
        (1, "Ada Lovelace", "ada@example.com", "enterprise"),
        (2, "Grace Hopper", "grace@example.com", "pro"),
        (3, "Alan Turing", "alan@example.com", "free"),
    ],
    "orders": [
        (1, 1, "API credits", 500.0, "paid"),
        (2, 2, "Support plan", 120.0, "paid"),
        (3, 3, "API credits", 10.0, "pending"),
    ],
}


class DatabaseTool(BaseTool):
    name = "query_database"
    description = "Run a read-only SQL SELECT against the demo 'users'/'orders' tables, capped to 'limit' rows."

    def __init__(self, failure_engine: FailureEngine, db_path: str) -> None:
        super().__init__(failure_engine)
        self._db_path = db_path
        self._seed()

    def _seed(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript(_SEED_SQL)
            for table, rows in _SEED_ROWS.items():
                if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
                    placeholders = ",".join("?" * len(rows[0]))
                    conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
            conn.commit()
        finally:
            conn.close()

    def _run(self, query: str, limit: int = 100) -> str:
        if not query.strip().lower().startswith("select"):
            return "Error: only SELECT statements are permitted."
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(query)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()[:limit]
        except sqlite3.Error as exc:
            return f"Error: {exc}"
        finally:
            conn.close()
        if not rows:
            return "[]"
        return str([dict(zip(columns, row)) for row in rows])
