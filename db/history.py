"""SQLite history store for transcriptions."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "history.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                raw_text   TEXT NOT NULL,
                final_text TEXT NOT NULL,
                mode       TEXT NOT NULL,
                duration_s REAL,
                injected   INTEGER NOT NULL DEFAULT 0
            )
        """)


def save(
    raw_text: str,
    final_text: str,
    mode: str,
    duration_s: float | None = None,
    injected: bool = False,
) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO history (created_at, raw_text, final_text, mode, duration_s, injected) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                raw_text,
                final_text,
                mode,
                duration_s,
                1 if injected else 0,
            ),
        )
        return cur.lastrowid


def get_recent(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(entry_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
    return dict(row) if row else None


def delete(entry_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM history WHERE id = ?", (entry_id,))


def clear_all() -> None:
    with _conn() as con:
        con.execute("DELETE FROM history")
